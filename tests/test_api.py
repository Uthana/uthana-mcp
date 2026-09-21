import json

import httpx
import pytest

from uthana_mcp.api import APIError, UthanaAPI
from uthana_mcp.validation import motion_metadata, normalize_job


@pytest.mark.parametrize(
    "domain", ["example.com", "staging.uthana.dev.evil", "https://staging.uthana.com", "staging.uthana.com.evil"]
)
def test_rejects_unapproved_domains(domain):
    with pytest.raises(ValueError):
        UthanaAPI("fake", domain)


async def test_correct_staging_configuration():
    api = UthanaAPI("fake", "staging.uthana.com")
    await api.close()


@pytest.mark.parametrize(
    "result",
    [
        {"result": {"id": "motion1"}},
        {"id": "motion1"},
        {"motion_id": "motion1"},
        json.dumps({"result": {"id": "motion1"}}),
        {"result": json.dumps({"motion_id": "motion1"})},
    ],
)
def test_completed_job_response_shapes(result):
    normalized = normalize_job({"id": "job1", "status": "FINISHED", "result": result})
    assert normalized["motion_id"] == "motion1" and normalized["state"] == "complete"
    assert normalized["terminal"] and normalized["poll_after_seconds"] is None


def test_finished_without_id_and_failed_are_not_success():
    assert normalize_job({"id": "job1", "status": "FINISHED", "result": "bad-json"})["state"] == "unresolved"
    assert normalize_job({"id": "job1", "status": "FAILED", "result": None})["state"] == "failed"


def test_native_metadata_validation():
    motion = {
        "id": "motion1",
        "name": "Jump",
        "assets": [
            {
                "id": "bundle1",
                "uid": "motion1",
                "type": "bundle",
                "sha256": "a" * 64,
                "metadata": {"fps": 30, "frame_count": 120, "duration": 4},
            }
        ],
    }
    result = motion_metadata(motion)
    assert result["duration_seconds"] == 4
    assert result["last_sample_seconds"] == 119 / 30
    motion["assets"][0]["metadata"]["duration"] = 8
    with pytest.raises(ValueError, match="disagrees"):
        motion_metadata(motion)


@pytest.mark.parametrize("domain", ["staging.uthana.com", "uthana.com", "devbox.uthana.dev"])
async def test_api_graphql_documents_and_export_routes(domain):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == domain
        assert request.headers["authorization"] == "Basic ZmFrZTo="
        if request.url.path == "/graphql":
            document = json.loads(request.content)
            if "create_text_to_motion_job(" in document["query"]:
                assert document["variables"]["length"] == 4
                assert document["variables"]["model"] == "text-to-motion-3.0"
                assert document["variables"]["rewrite_prompt"] is True
                return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})
            if "trim_and_loop_motion(" in document["query"]:
                assert "loop: false" in document["query"]
                assert document["variables"]["start"] == 0.25
                return httpx.Response(200, json={"data": {"trim_and_loop_motion": {"motion": {"id": "trimmed1"}}}})
        if request.url.path.endswith("preview.png"):
            return httpx.Response(200, content=b"apng-fixture")
        assert request.url.path == "/motion/file/motion_viewer/roblox1/motion1/fbx/roblox1-motion1.fbx"
        assert dict(request.url.params) == {
            "fps": "30",
            "no_mesh": "false",
            "in_place": "true",
            "roblox_compatible": "true",
        }
        return httpx.Response(200, content=b"export")

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        assert (await api.generate("Jump", 4, "tar"))["job_id"] == "job1"
        assert (await api.trim("motion1", 0.25, 0.75, "Middle"))["motion_id"] == "trimmed1"
        await api.preview("motion1", "tar", "apng")
        await api.download("motion1", "roblox1", "fbx", 30, True, True, True)
        assert len(requests) == 4
    finally:
        await api.close()


@pytest.mark.parametrize("auto_rig", [False, True])
@pytest.mark.parametrize("domain", ["staging.uthana.com", "uthana.com", "devbox.uthana.dev"])
async def test_multipart_upload_and_save_contracts(auto_rig, domain):
    def respond(request):
        content = request.content.decode()
        if "multipart/form-data" in request.headers["content-type"]:
            assert '"0": ["variables.file"]' in content
            assert "fixture-bytes" in content
            if "create_video_to_motion(" in content:
                assert '"model": "video-to-motion-2.1"' in content
                return httpx.Response(200, json={"data": {"create_video_to_motion": {"job": {"id": "job1"}}}})
            assert f'"auto_rig": {str(auto_rig).lower()}' in content
            assert '"auto_rig_front_facing": true' in content
            assert '"include_fingers": true' in content
            return httpx.Response(200, json={"data": {"create_character": {"character": {"id": "character1"}}}})
        body = json.loads(content)
        assert body["variables"] == {
            "gltf": "{}",
            "motionName": "Saved",
            "sourceMotionId": "motion1",
            "characterId": "character1",
        }
        return httpx.Response(200, json={"data": {"create_motion_from_gltf": {"motion": {"id": "saved1"}}}})

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        assert (await api.video("walk.mp4", b"fixture-bytes", "Walk", "video-to-motion-2.1"))["job_id"] == "job1"
        assert (await api.upload_character("rig.fbx", b"fixture-bytes", "Rig", auto_rig))[
            "character_id"
        ] == "character1"
        assert (await api.save("{}", "Saved", "motion1", "character1"))["motion_id"] == "saved1"
    finally:
        await api.close()


@pytest.mark.parametrize("status", [302, 401, 500])
@pytest.mark.parametrize("domain", ["staging.uthana.com", "uthana.com", "devbox.uthana.dev"])
async def test_errors_do_not_expose_body_or_follow_redirects(status, domain):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, text="secret-provider-detail", headers={"location": "https://elsewhere.invalid"})

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.job("job1")
        assert "secret" not in str(exc.value) and len(requests) == 1
    finally:
        await api.close()


async def test_partial_graphql_errors_never_count_as_success():
    api = UthanaAPI(
        "fake",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"data": {"job": {"id": "job1"}}, "errors": [{"message": "private-provider-detail"}]}
            )
        ),
    )
    try:
        with pytest.raises(APIError, match="GraphQL request failed"):
            await api.job("job1")
    finally:
        await api.close()


@pytest.mark.parametrize("domain", ["staging.uthana.com", "uthana.com", "devbox.uthana.dev"])
async def test_catalog_usage_eligibility_and_export_effects_contracts(domain):
    seen = []

    def respond(request):
        seen.append(request)
        assert request.url.host == domain
        if request.url.path == "/graphql":
            body = json.loads(request.content)
            query = body["query"]
            assert query.lstrip().startswith("query") and "mutation" not in query
            if "MotionCatalog" in query:
                assert 'motions(app_ids: ["motion_viewer"])' in query
                assert "org { id }" in query and "id org_id name created tags" in query
                assert "label_search" not in query
                return httpx.Response(200, json={"data": {"org": {"id": "o1"}, "motions": []}})
            if "Usage" in query:
                assert "subscription { status secs_per_month characters }" in query
                assert "payg_prices { model_key billing_unit unit_price }" in query
                assert "payg_total_usd" in query
                assert "email" not in query and "users" not in query
                return httpx.Response(200, json={"data": {"org": {"payg_enabled": True}}})
            assert "motion_download_allowed(motion_id: $motion_id, character_id: $character_id)" in query
            assert body["variables"] == {"motion_id": "m1", "character_id": "c1"}
            return httpx.Response(
                200, json={"data": {"motion_download_allowed": {"allowed": False, "reason": "Limit"}}}
            )
        assert request.url.path == "/motion/file/motion_viewer/c1/m1/fbx/c1-m1.fbx"
        assert dict(request.url.params) == {
            "fps": "30",
            "no_mesh": "false",
            "in_place": "true",
            "roblox_compatible": "false",
            "speed_multiplier": "0.5",
            "torso_only": "true",
        }
        return httpx.Response(200, content=b"export")

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        assert (await api.motion_catalog())["motions"] == []
        assert (await api.usage())["org"]["payg_enabled"] is True
        assert (await api.download_allowed("m1", "c1"))["allowed"] is False
        await api.download("m1", "c1", "fbx", 30, True, True, False, 0.5, True)
        assert len(seen) == 4
    finally:
        await api.close()


@pytest.mark.parametrize("allowed", [None, "false"])
async def test_eligibility_null_is_unknown_and_strings_are_not_booleans(allowed):
    api = UthanaAPI(
        "fake",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"data": {"motion_download_allowed": {"allowed": allowed, "reason": None}}},
            )
        ),
    )
    try:
        if allowed is None:
            assert (await api.download_allowed("m1", "c1"))["allowed"] is None
        else:
            with pytest.raises(APIError, match="Invalid download eligibility"):
                await api.download_allowed("m1", "c1")
    finally:
        await api.close()
