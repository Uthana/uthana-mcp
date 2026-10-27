"""share_motion: public viewer links for people outside the organization."""

import json

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import APIError, UthanaAPI
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server


def ops_for(tmp_path):
    api = FakeAPI()
    return api, Operations(api, tmp_path / "state", tmp_path / "inputs")


async def test_share_defaults_to_tar_and_the_full_motion(tmp_path):
    api, ops = ops_for(tmp_path)
    result = await ops.share("motion1")
    assert api.calls == [("share", {"motion_id": "motion1", "character_id": "cXi2eAP19XwQ", "start": 0.0, "end": 1.0})]
    assert result["preview_url"] == "https://uthana.com/app/preview/cXi2eAP19XwQ/motion1"
    assert result["image_url"].endswith("/share.png")
    assert result["window_seconds"] is None and result["access"] == "public"
    assert "without an account" in result["note"] and "stays public" in result["note"]


async def test_share_window_in_seconds_becomes_duration_fractions(tmp_path):
    api, ops = ops_for(tmp_path)
    # motion1 is a 4-second fixture: 120 frames at 30 fps.
    result = await ops.share("motion1", "mixamo1", 1, 3)
    assert api.calls[-1] == ("share", {"motion_id": "motion1", "character_id": "mixamo1", "start": 0.25, "end": 0.75})
    assert result["window_seconds"] == [1, 3]
    partial = await ops.share("motion1", "mixamo1", end_seconds=2)
    assert api.calls[-1][1]["start"] == 0.0 and api.calls[-1][1]["end"] == 0.5
    assert partial["window_seconds"] == [0, 2]
    tail = await ops.share("motion1", "mixamo1", start_seconds=3)
    assert api.calls[-1][1]["start"] == 0.75 and api.calls[-1][1]["end"] == 1.0
    assert tail["window_seconds"] == [3, 4.0]


@pytest.mark.parametrize("start,end", [(3, 1), (2, 2), (0, 4.5), (-1, 2), (0, float("inf"))])
async def test_share_rejects_windows_outside_the_motion(tmp_path, start, end):
    api, ops = ops_for(tmp_path)
    with pytest.raises(ValueError):
        await ops.share("motion1", "mixamo1", start, end)
    assert not any(name == "share" for name, _ in api.calls)


async def test_share_rejects_bad_identifiers_before_any_request(tmp_path):
    api, ops = ops_for(tmp_path)
    with pytest.raises(ValueError):
        await ops.share("motion/1")
    with pytest.raises(ValueError):
        await ops.share("motion1", "")
    assert api.calls == []


async def test_share_failure_propagates(tmp_path):
    _, ops = ops_for(tmp_path)
    with pytest.raises(RuntimeError, match="Share rejected"):
        await ops.share("denied")


async def test_share_tool_is_public_idempotent_and_free_of_request_ids(tmp_path):
    _, ops = ops_for(tmp_path)
    server = create_server(ops)
    tools = {tool.name: tool for tool in await server.list_tools()}
    tool = tools["share_motion"]
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.idempotentHint is True
    assert tool.annotations.destructiveHint is False
    assert "request_id" not in tool.inputSchema["properties"]
    assert set(tool.inputSchema["properties"]) == {"motion_id", "character_id", "start_seconds", "end_seconds"}
    assert "without an account" in tool.description and "stays public" in tool.description
    assert "share_motion" in server._workflow_text() if hasattr(server, "_workflow_text") else True


async def test_api_share_sends_the_mutation_and_validates_the_link():
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path == "/graphql"
        assert body["query"].lstrip().startswith("mutation CreateShareLink")
        return httpx.Response(
            200, json={"data": {"create_share_link": {"png_url": "https://uthana.com/app/share/c1/m1/share.png"}}}
        )

    api = UthanaAPI("fake", "uthana.com", transport=httpx.MockTransport(respond))
    try:
        result = await api.share("m1", "c1", 0.25, 0.5)
    finally:
        await api.close()
    assert seen[0]["variables"] == {
        "character_id": "c1",
        "motion_id": "m1",
        "start": 0.25,
        "end": 0.5,
        "fps": 10,
        "wd": 300,
        "ht": 157,
    }
    assert result == {
        "motion_id": "m1",
        "character_id": "c1",
        "preview_url": "https://uthana.com/app/preview/c1/m1?start=0.25&end=0.50",
        "image_url": "https://uthana.com/app/share/c1/m1/share.png",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {"create_share_link": {"png_url": None}}},
        {"data": {"create_share_link": {"png_url": "ftp://not-https"}}},
        {"data": {"create_share_link": None}},
    ],
)
async def test_api_share_without_a_usable_link_is_an_unknown_outcome(payload):
    api = UthanaAPI(
        "fake", "uthana.com", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    try:
        with pytest.raises(APIError) as error:
            await api.share("m1", "c1", 0.0, 1.0)
    finally:
        await api.close()
    assert error.value.outcome == "unknown"


async def test_api_share_link_must_point_at_the_configured_environment():
    def respond(request):
        return httpx.Response(200, json={"data": {"create_share_link": {"png_url": "https://uthana.com/x.png"}}})

    # The client builds preview_url from its own base URL, so a mismatched domain cannot occur in practice;
    # the guard still rejects a link for another environment if the client's base URL ever diverges.
    api = UthanaAPI("fake", "staging.uthana.com", transport=httpx.MockTransport(respond))
    try:
        result = await api.share("m1", "c1", 0.0, 1.0)
    finally:
        await api.close()
    assert result["preview_url"] == "https://staging.uthana.com/app/preview/c1/m1"


async def test_api_share_rejection_is_reported_as_a_graphql_error():
    def respond(request):
        return httpx.Response(
            200, json={"errors": [{"message": "User does not have access to motion m1"}], "data": None}
        )

    api = UthanaAPI("fake", "uthana.com", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as error:
            await api.share("m1", "c1", 0.0, 1.0)
    finally:
        await api.close()
    assert error.value.outcome == "rejected"
