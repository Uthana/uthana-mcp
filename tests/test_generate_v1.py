import json

import httpx
import pytest

from uthana_mcp.api import APIError, UthanaAPI


async def test_v1_uses_selected_character_and_no_duration():
    def respond(request):
        payload = json.loads(request.content)
        assert "create_text_to_motion(" in payload["query"]
        variables = payload["variables"]
        assert variables["model"] == "text-to-motion"
        assert variables["character_id"] == "selected"
        assert variables.get("length") is None
        assert variables["foot_ik"] is True
        return httpx.Response(200, json={"data": {"create_text_to_motion": {"motion": {"id": "saved"}}}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        assert await api.generate_v1("Walk", character_id="selected") == {
            "motion_id": "saved",
            "character_id": "selected",
        }
    finally:
        await api.close()


async def test_v1_preserves_rejected_authentication_outcome():
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda request: httpx.Response(401)))
    try:
        with pytest.raises(APIError) as caught:
            await api.generate_v1("Walk", character_id="selected")
        assert caught.value.outcome == "rejected"
    finally:
        await api.close()
