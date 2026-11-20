"""Charged library search: client routing, receipts, billing identity, and validation."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.billing import PUBLISHED_MODELS, estimate_cost
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server


async def test_api_sends_nearest_neighbor_and_normalizes_score() -> None:
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        motion = {"id": "mLib1", "name": "NN: wave", "tags": {"Distance": 0.81234567, "Nearest": "lHidden"}}
        return httpx.Response(200, json={"data": {"create_text_to_motion": {"motion": motion}}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        result = await api.library_search("wave", "c1")
    finally:
        await api.close()
    assert 'model: "nearest-neighbor"' in seen[0]["query"]
    assert seen[0]["variables"] == {"prompt": "wave", "character_id": "c1"}
    assert result == {"motion_id": "mLib1", "character_id": "c1", "name": "NN: wave", "match_score": 0.8123}
    assert "lHidden" not in str(result)


async def test_receipt_is_charged_replayable_and_never_exhaustive(tmp_path: Path) -> None:
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    first = await ops.library_search("lib", "a person waving")
    assert first["motion_id"] == "motion1" and first["candidates_returned"] == 1
    assert first["exhaustive"] is False and first["result_kind"] == "copied_library_match"
    assert first["billing"]["model"] == "library-search-1.0"
    assert first["billing"]["cost_status"] == "unmeasured" and first["credits_used"] is None
    again = await ops.library_search("lib", "a person waving")
    assert again["replayed"] and len(api.calls) == 1
    with pytest.raises(ValueError, match="different arguments"):
        await ops.library_search("lib", "a person jumping")


@pytest.mark.parametrize("prompt", ["", "x" * 1001, None])
async def test_invalid_prompt_does_not_submit(tmp_path: Path, prompt: Any) -> None:
    api = FakeAPI()
    with pytest.raises(ValueError):
        await Operations(api, tmp_path).library_search("r", prompt)
    assert api.calls == []


def test_library_search_is_a_published_per_second_price() -> None:
    assert PUBLISHED_MODELS["library-search-1.0"] == "nearest-neighbor"
    rates = [{"model_key": "nearest-neighbor", "billing_unit": "second", "unit_price": "0.10"}]
    assert estimate_cost(rates, "library-search-1.0", 5)["estimated_cost_usd"] == "0.5000"


async def test_estimate_tool_enum_matches_published_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTHANA_API_KEY", "")
    tools = {tool.name: tool for tool in await create_server().list_tools()}
    assert set(tools["estimate_model_cost"].inputSchema["properties"]["model"]["enum"]) == set(PUBLISHED_MODELS)
    library = tools["copy_best_library_motion"]
    assert library.annotations.readOnlyHint is False and library.annotations.idempotentHint is False
