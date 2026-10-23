from copy import deepcopy

import pytest
from fakes import FakeAPI

from uthana_mcp.api import APIError
from uthana_mcp.catalog import usage_snapshot
from uthana_mcp.operations import Operations


def motion(id, name, org="org1", method="TextToMotion"):
    return {"id": id, "org_id": org, "name": name, "tags": {"Method": method}}


async def test_name_search_origin_filters_and_pagination(tmp_path):
    api = FakeAPI()
    rows = [
        motion("m1", "Slow WALK"),
        motion("m2", "Walk fast"),
        motion("m3", "walk slow example", "public", "Mocap"),
        motion("m1", "Slow WALK"),
    ]

    async def catalog():
        return {"org": {"id": "org1"}, "motions": rows}

    api.motion_catalog = catalog
    ops = Operations(api, tmp_path)
    first = await ops.motions("walk SLOW", limit=1)
    assert first["motions"][0]["motion_id"] == "m1"
    assert first["motions"][0]["source"] == "organization"
    assert first["matched_in_available_window"] == 2 and first["scanned_count"] == 3
    second = await ops.motions("walk SLOW", offset=first["next_offset"], limit=1)
    assert second["motions"][0]["source"] == "uthana_example" and second["next_offset"] is None
    own = await ops.motions("walk", source="organization")
    assert [r["motion_id"] for r in own["motions"]] == ["m1", "m2"]
    examples = await ops.motions(source="examples", method="mocap")
    assert [r["motion_id"] for r in examples["motions"]] == ["m3"]
    assert (await ops.motions(method="VideoToMotion"))["motions"] == []
    empty = await ops.motions("unavailable")
    assert empty["motions"] == [] and empty["full_library_searched"] is False
    assert "No semantic search" in empty["scope_note"]


async def test_window_limit_reported_before_filters(tmp_path):
    api = FakeAPI()

    async def catalog():
        return {"org": {"id": "org1"}, "motions": [motion(f"m{i}", "Jump") for i in range(1000)]}

    api.motion_catalog = catalog
    result = await Operations(api, tmp_path).motions("missing")
    assert result["motions"] == [] and result["organization_window_may_be_truncated"] is True
    assert result["next_offset"] is None and result["scanned_count"] == 1000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": "x" * 201},
        {"source": "all_shared"},
        {"offset": -1},
        {"offset": True},
        {"limit": 101},
        {"limit": False},
        {"method": " "},
    ],
)
async def test_invalid_catalog_arguments_never_call_provider(tmp_path, kwargs):
    api = FakeAPI()
    with pytest.raises(ValueError):
        await Operations(api, tmp_path).motions(**kwargs)
    assert api.calls == []


async def test_missing_org_does_not_mislabel_motions_as_examples(tmp_path):
    api = FakeAPI()

    async def catalog():
        return {"org": None, "motions": [motion("m1", "Walk")]}

    api.motion_catalog = catalog
    with pytest.raises(APIError, match="organization unavailable"):
        await Operations(api, tmp_path).motions()


def usage_data():
    return {
        "org": {
            "payg_enabled": False,
            "payg_total_usd": None,
            "payg_auto_recharge_enabled": False,
            "motion_download_secs_per_month": 30,
            "motion_download_secs_per_month_remaining": 80,
            "characters_allowed": 2,
            "characters_allowed_remaining": 3,
        },
        "subscription": {"status": "active", "secs_per_month": 100, "characters": 4},
        "payg_prices": [{"model_key": "text-to-motion-3.0", "billing_unit": "second", "unit_price": "0.1250"}],
    }


def test_active_subscription_overrides_org_quota_without_mixing_units():
    result = usage_snapshot(usage_data())
    assert result["monthly_downloads"] == {
        "unit": "motion_seconds",
        "quota_applies_to_billing_mode": True,
        "limit": 100,
        "remaining": 80,
    }
    assert result["monthly_characters"]["limit"] == 4
    assert result["payg"]["balance_usd"] is None
    assert result["payg"]["rates"][0]["unit_price_usd"] == "0.1250"
    assert result["operation_cost_known"] is False


def test_inactive_subscription_and_known_zero_are_distinct_from_missing():
    data = usage_data()
    data["subscription"]["status"] = "canceled"
    data["org"]["motion_download_secs_per_month_remaining"] = 0
    result = usage_snapshot(data)
    assert result["monthly_downloads"]["limit"] == 30
    assert result["monthly_downloads"]["remaining"] == 0
    data["org"]["motion_download_secs_per_month_remaining"] = None
    assert usage_snapshot(data)["monthly_downloads"]["remaining"] is None


def test_payg_does_not_present_legacy_quota_or_int_sentinel_as_limit():
    data = usage_data()
    data["org"].update(
        payg_enabled=True,
        payg_total_usd="10.0101",
        payg_auto_recharge_enabled=True,
        motion_download_secs_per_month_remaining=0,
        characters_allowed_remaining=2**31 - 1,
    )
    result = usage_snapshot(data)
    assert result["payg"]["balance_usd"] == "10.0101"
    assert result["payg"]["auto_recharge_enabled"] is True
    assert result["monthly_downloads"]["quota_applies_to_billing_mode"] is False
    assert result["monthly_downloads"]["remaining"] is None
    assert result["monthly_characters"]["remaining"] is None
    assert result["monthly_characters"]["limit"] is None


def test_missing_billing_fields_stay_unknown_and_bad_money_is_rejected():
    result = usage_snapshot({"org": {}})
    assert result["payg_enabled"] is None
    assert result["payg"]["rates"] is None
    assert result["monthly_downloads"]["quota_applies_to_billing_mode"] is None
    for value in ("NaN", "Infinity", "invalid", True):
        data = deepcopy(usage_data())
        data["org"]["payg_total_usd"] = value
        with pytest.raises(APIError, match="USD"):
            usage_snapshot(data)
    with pytest.raises(APIError, match="unavailable"):
        usage_snapshot({"org": None})


async def test_usage_and_specific_eligibility_are_read_only(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    usage = await ops.usage()
    assert usage["monthly_downloads"]["remaining"] == 15
    denied = await ops.download_allowed("denied", "mixamo1")
    allowed = await ops.download_allowed("motion1", "mixamo1")
    assert denied["allowed"] is False and allowed["allowed"] is True
    assert allowed["reserves_allowance"] is False and allowed["operation_cost_known"] is False
    assert [c[0] for c in api.calls] == ["usage", "download_allowed", "download_allowed"]
    assert len(list(ops.store.directory.iterdir())) == 1  # Only the SQLite store; no export artifacts.
