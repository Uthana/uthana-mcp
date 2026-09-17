import json

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import APIError, UthanaAPI
from uthana_mcp.billing import estimate_cost, receipt_billing
from uthana_mcp.catalog import usage_snapshot
from uthana_mcp.operations import Operations


async def test_v2_and_locomotion_api_contracts():
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        if "create_text_to_motion(" in body["query"]:
            assert body["variables"] == {
                "prompt": "Walk",
                "character_id": "c1",
                "length": 4,
                "model": "text-to-motion-bucmd",
                "foot_ik": True,
                "cfg_scale": None,
                "seed": None,
                "retargeting_ik": None,
            }
            return httpx.Response(200, json={"data": {"create_text_to_motion": {"motion": {"id": "m1"}}}})
        if "locomotion_styles" in body["query"]:
            return httpx.Response(200, json={"data": {"locomotion_styles": ["neutral_male_a"]}})
        if "payg_prices" in body["query"]:
            return httpx.Response(200, json={"data": {"payg_prices": []}})
        assert "create_locomotion" in body["query"]
        assert body["variables"] == {
            "character_id": "c1",
            "strides": 3,
            "move_speed": 1.2,
            "style_id": "neutral_male_a",
            "travel_angle": 90,
        }
        return httpx.Response(200, json={"data": {"create_locomotion": {"motion": {"id": "m2"}}}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        assert (await api.generate_v2("Walk", 4, "c1"))["motion_id"] == "m1"
        assert await api.locomotion_styles() == ["neutral_male_a"]
        assert (await api.locomotion("c1", 3, 1.2, "neutral_male_a", 90))["motion_id"] == "m2"
        assert await api.prices() == [] and len(seen) == 4
    finally:
        await api.close()


async def test_new_generation_receipts_recover_and_keep_model_identity(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    v2 = await ops.generate_v2("v2", "Walk")
    assert v2["billing"]["model"] == "text-to-motion-2.0" and v2["credits_used"] is None
    assert (await ops.generate_v2("v2", "Walk"))["replayed"]
    result = await ops.locomotion("loco", strides=3)
    assert result["billing"]["model"] == "locomotion-1.0" and result["loop_intended"]

    async def unavailable():
        raise RuntimeError("styles unavailable")

    api.locomotion_styles = unavailable
    assert (await ops.locomotion("loco", strides=3))["replayed"]
    with pytest.raises(ValueError, match="different arguments"):
        await ops.locomotion("loco", strides=4)
    assert [c[0] for c in api.calls] == ["generate_v2", "locomotion"]


@pytest.mark.parametrize("duration", [3, 10.4, 4.1, float("nan")])
async def test_v2_invalid_timing_does_not_submit(tmp_path, duration):
    api = FakeAPI()
    with pytest.raises(ValueError):
        await Operations(api, tmp_path).generate_v2("r", "Walk", duration)
    assert api.calls == []


@pytest.mark.parametrize(
    "kwargs",
    [{"strides": True}, {"strides": 6}, {"move_speed": 0}, {"travel_angle": float("inf")}, {"style_id": "invented"}],
)
async def test_invalid_locomotion_has_no_mutation_or_unknown_receipt(tmp_path, kwargs):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(ValueError):
        await ops.locomotion("r", **kwargs)
    assert api.calls == [] and ops.store.get_request("r")["state"] == "not_found"


async def test_locomotion_timeout_is_never_resubmitted(tmp_path):
    api = FakeAPI()

    async def fail(**args):
        api.calls.append(("locomotion", args))
        raise TimeoutError()

    api.locomotion = fail
    ops = Operations(api, tmp_path)
    with pytest.raises(RuntimeError):
        await ops.locomotion("r")
    with pytest.raises(ValueError, match="unresolved"):
        await ops.locomotion("r")
    assert len(api.calls) == 1


async def test_estimates_use_live_rates_and_are_not_charges(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    v2 = await ops.estimate_cost("text-to-motion-2.0", 4)
    v3 = await ops.estimate_cost("text-to-motion-3.0", 4)
    rig = await ops.estimate_cost("autorig", 2)
    assert v2["estimated_cost_usd"] == "0.1200" and v3["estimated_cost_usd"] == "0.4000"
    assert rig["estimated_cost_usd"] == "0.3000"
    assert v3["actual_cost_usd"] is None and v3["api_mcp_fee_usd"] == "0"
    assert api.calls == []
    prices = await api.prices()
    prices[0]["unit_price"] = "0.04"
    assert estimate_cost(prices, "text-to-motion-2.0", 4)["estimated_cost_usd"] == "0.1600"
    assert "staging" not in estimate_cost(prices, "text-to-motion-3.0", 4)["rate_source"]
    for rates in ([], [prices[0], prices[0]], [{**prices[0], "billing_unit": "rig"}]):
        with pytest.raises(APIError):
            estimate_cost(rates, "text-to-motion-2.0", 4)
    for model, quantity in (("invented", 4), ("autorig", 1.5), ("text-to-motion-3.0", 0)):
        with pytest.raises(ValueError):
            estimate_cost(prices, model, quantity)


def test_free_operations_and_paid_autorig_are_distinguished():
    for operation, args in [("trim", {}), ("save", {}), ("download", {}), ("upload_character", {"auto_rig": False})]:
        billing = receipt_billing(operation, args)
        assert billing["cost_status"] == "free_by_policy" and billing["actual_cost_usd"] == "0"
    assert receipt_billing("upload_character", {"auto_rig": True})["model"] == "autorig"
    assert receipt_billing("upload_character", {"auto_rig": True})["actual_cost_usd"] is None
    assert receipt_billing("unknown_future_operation", {})["actual_cost_usd"] is None


def test_usage_catalog_excludes_unpublished_backend_skus():
    result = usage_snapshot(
        {
            "org": {},
            "payg_prices": [
                {"model_key": "nearest-neighbor", "billing_unit": "second", "unit_price": "0.10"},
                {"model_key": "text-to-motion-bucmd", "billing_unit": "second", "unit_price": "0.03"},
            ],
        }
    )
    assert len(result["payg"]["rates"]) == 1
    assert result["payg"]["rates"][0]["model"] == "text-to-motion-2.0"
    assert result["api_mcp_fee_usd"] == "0"


async def test_free_receipt_survives_restart_and_old_receipts_are_not_repriced(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    result = await ops.download("free", "motion1")
    assert result["credits_used"] == 0 and result["usage_status"] == "free_by_policy"
    restarted = Operations(api, tmp_path)
    assert (await restarted.download("free", "motion1"))["billing"] == result["billing"]
    # Historical receipts retain recorded accounting rather than rewriting old charges.
    with ops.store.connect() as db:
        data = json.loads(db.execute("SELECT result FROM requests WHERE id='free'").fetchone()[0])
        data.pop("billing")
        data["credits_used"] = None
        db.execute("UPDATE requests SET result=? WHERE id='free'", (json.dumps(data),))
    old = await restarted.download("free", "motion1")
    assert old["credits_used"] is None and "billing" not in old and len(api.calls) == 1


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-0.03", "invalid"])
def test_invalid_rates_cannot_be_reported_as_a_price(price):
    with pytest.raises(APIError, match="Invalid published"):
        estimate_cost(
            [{"model_key": "text-to-motion-bucmd", "billing_unit": "second", "unit_price": price}],
            "text-to-motion-2.0",
            4,
        )
