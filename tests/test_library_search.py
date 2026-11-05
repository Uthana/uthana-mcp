"""Charged library search: client routing, receipts, billing identity, and validation."""

import json

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.billing import PUBLISHED_MODELS, estimate_cost
from uthana_mcp.operations import Operations


async def test_api_sends_nearest_neighbor_and_normalizes_score():
    seen = []

    def respond(request):
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


async def test_receipt_is_charged_replayable_and_never_exhaustive(tmp_path):
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
async def test_invalid_prompt_does_not_submit(tmp_path, prompt):
    api = FakeAPI()
    with pytest.raises(ValueError):
        await Operations(api, tmp_path).library_search("r", prompt)
    assert api.calls == []


def test_library_search_is_a_published_per_second_price():
    assert PUBLISHED_MODELS["library-search-1.0"] == "nearest-neighbor"
    rates = [{"model_key": "nearest-neighbor", "billing_unit": "second", "unit_price": "0.10"}]
    assert estimate_cost(rates, "library-search-1.0", 5)["estimated_cost_usd"] == "0.5000"
