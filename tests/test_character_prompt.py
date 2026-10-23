import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations


@pytest.fixture
def setup(tmp_path):
    api = FakeAPI()
    return api, Operations(api, tmp_path / "state", tmp_path)


async def test_preview_saves_images_and_replays(setup):
    api, ops = setup
    result = await ops.preview_character_from_prompt("prev1", "A warehouse worker in a hi-vis vest")
    assert result["stage"] == "previews_ready" and result["character_id"] == "promptchar1"
    assert [p["preview_index"] for p in result["previews"]] == [0, 1]
    assert all(p["artifact_id"] and p["width"] == 64 for p in result["previews"])
    assert result["billing"]["cost_status"] == "unmeasured"
    thumbnails = ops.character_preview_images(result)
    assert [index for index, _ in thumbnails] == [0, 1] and thumbnails[0][1][:2] == b"\xff\xd8"
    again = await ops.preview_character_from_prompt("prev1", "A warehouse worker in a hi-vis vest")
    assert again["replayed"] and sum(c[0] == "preview_prompt" for c in api.calls) == 1
    with pytest.raises(ValueError, match="different arguments"):
        await ops.preview_character_from_prompt("prev1", "Someone else")


async def test_missing_preview_image_keeps_character_id(setup):
    api, ops = setup

    async def broken(url, max_bytes=0):
        raise httpx.ConnectError("private storage URL with a signed credential")

    api.fetch_preview_image = broken
    result = await ops.preview_character_from_prompt("prev1", "A worker")
    assert result["character_id"] == "promptchar1"
    assert all("image_unavailable" in p and "artifact_id" not in p for p in result["previews"])
    assert ops.character_preview_images(result) == []
    assert "private storage" not in str(result)


async def test_finalize_uses_chosen_preview_and_prompt(setup):
    api, ops = setup
    await ops.preview_character_from_prompt("prev1", "A worker")
    created = await ops.create_character_from_prompt("char1", "prev1", 1, "Worker")
    assert created["character_id"] == "promptchar1" and created["stage"] == "character_created"
    assert created["billing"]["model"] == "character-gen-1.0"
    call = next(c[1] for c in api.calls if c[0] == "finalize_prompt")
    assert call == {
        "character_id": "promptchar1",
        "prompt": "A worker",
        "image_key": "preview1.png",
        "name": "Worker",
    }
    assert (await ops.create_character_from_prompt("char1", "prev1", 1, "Worker"))["replayed"]
    with pytest.raises(ValueError, match="different arguments"):
        await ops.create_character_from_prompt("char1", "prev1", 0, "Worker")


@pytest.mark.parametrize(
    "preview_request, index, message",
    [("missing", 0, "completed preview"), ("prev1", 5, "not in that preview list"), ("prev1", True, "whole number")],
)
async def test_finalize_rejects_bad_selection(setup, preview_request, index, message):
    api, ops = setup
    await ops.preview_character_from_prompt("prev1", "A worker")
    with pytest.raises(ValueError, match=message):
        await ops.create_character_from_prompt("char1", preview_request, index, "Worker")
    assert not any(c[0] == "finalize_prompt" for c in api.calls)


async def test_finalize_rejects_a_second_request_id_for_the_same_preview(setup):
    api, ops = setup
    await ops.preview_character_from_prompt("prev1", "A worker")
    await ops.create_character_from_prompt("char1", "prev1", 1, "Worker")
    with pytest.raises(ValueError, match="already finalized by a different request_id"):
        await ops.create_character_from_prompt("char2", "prev1", 1, "Worker")
    # The original finalizing request_id may still retry (for example with a corrected name).
    assert (await ops.create_character_from_prompt("char1", "prev1", 1, "Worker"))["replayed"]
    assert sum(c[0] == "finalize_prompt" for c in api.calls) == 1


async def test_invalid_selection_does_not_consume_preview(setup):
    api, ops = setup
    await ops.preview_character_from_prompt("prev1", "A worker")
    with pytest.raises(ValueError, match="not in that preview list"):
        await ops.create_character_from_prompt("invalid", "prev1", 99, "Worker")
    assert "finalized_by" not in ops.store.get_request("prev1")["result"]
    created = await ops.create_character_from_prompt("corrected", "prev1", 0, "Worker")
    assert created["character_id"] == "promptchar1"
    assert sum(c[0] == "finalize_prompt" for c in api.calls) == 1


async def test_conflicting_request_id_does_not_consume_another_preview(setup):
    api, ops = setup
    await ops.preview_character_from_prompt("prev1", "A worker")
    await ops.preview_character_from_prompt("prev2", "An athlete")
    await ops.create_character_from_prompt("used", "prev1", 0, "Worker")
    with pytest.raises(ValueError, match="different arguments"):
        await ops.create_character_from_prompt("used", "prev2", 0, "Athlete")
    assert "finalized_by" not in ops.store.get_request("prev2")["result"]
    await ops.create_character_from_prompt("new", "prev2", 0, "Athlete")
    assert sum(c[0] == "finalize_prompt" for c in api.calls) == 2


@pytest.mark.parametrize(
    "domain,url,authenticated",
    [
        ("uthana.com", "https://uthana.com/preview.png", True),
        ("uthana.com", "https://images.uthana.com/preview.png", False),
        ("uthana.com", "https://uthana.com:8443/preview.png", False),
        ("uthana.com:8443", "https://uthana.com:8443/preview.png", True),
        ("uthana.com:8443", "https://uthana.com/preview.png", False),
    ],
)
async def test_preview_credentials_require_exact_origin(domain, url, authenticated):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"preview")

    api = UthanaAPI("test-key", domain, transport=httpx.MockTransport(handler))
    try:
        assert await api.fetch_preview_image(url) == b"preview"
        assert ("authorization" in seen[0].headers) is authenticated
    finally:
        await api.close()


async def test_authenticated_preview_failure_is_redacted():
    api = UthanaAPI(
        "test-key",
        transport=httpx.MockTransport(lambda request: httpx.Response(403, text="private-provider-detail")),
    )
    try:
        with pytest.raises(APIError) as error:
            await api.fetch_preview_image("https://uthana.com/preview.png")
        assert error.value.category == "permission"
        assert "private-provider-detail" not in str(error.value)
    finally:
        await api.close()


async def test_finalize_rejects_other_operation_receipts(setup, tmp_path):
    api, ops = setup
    await ops.generate("gen1", "walk")
    with pytest.raises(ValueError, match="completed preview"):
        await ops.create_character_from_prompt("char1", "gen1", 0, "Worker")


async def test_preview_fetch_sends_key_only_to_uthana_host():
    seen = []

    def handler(request):
        seen.append((request.url.host, request.headers.get("authorization")))
        return httpx.Response(200, content=b"png-bytes")

    api = UthanaAPI("secret-key", "uthana.com", transport=httpx.MockTransport(handler))
    assert await api.fetch_preview_image("https://uthana.com/preview/0.png") == b"png-bytes"
    assert seen[-1] == ("uthana.com", seen[-1][1]) and seen[-1][1] is not None
    assert await api.fetch_preview_image("https://bucket.storage.example/0.png?sig=1") == b"png-bytes"
    assert seen[-1] == ("bucket.storage.example", None)
    assert await api.fetch_preview_image("https://uthana.com.evil.example/0.png") == b"png-bytes"
    assert seen[-1] == ("uthana.com.evil.example", None)
    with pytest.raises(Exception, match="HTTPS"):
        await api.fetch_preview_image("http://uthana.com/preview/0.png")


async def test_preview_fetch_bounds_size_and_status():
    def handler(request):
        if request.url.path == "/big.png":
            return httpx.Response(200, content=b"x" * 2048)
        return httpx.Response(302, headers={"location": "https://elsewhere.example/"})

    api = UthanaAPI("secret-key", "uthana.com", transport=httpx.MockTransport(handler))
    with pytest.raises(Exception, match="size limit"):
        await api.fetch_preview_image("https://storage.example/big.png", max_bytes=1024)
    with pytest.raises(Exception, match="HTTP 302"):
        await api.fetch_preview_image("https://storage.example/redirect.png")
