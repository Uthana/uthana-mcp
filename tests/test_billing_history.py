import pytest
from fakes import FakeAPI

from uthana_mcp.api import APIError
from uthana_mcp.billing_history import billing_history_page, ledger_request
from uthana_mcp.operations import Operations

ROWS = [
    {
        "id": "pl5",
        "created": "2026-11-03T10:00:00Z",
        "type": "debit",
        "total_usd": "0.2500",
        "balance_before": "10.0000",
        "balance_after": "9.7500",
        "model": "text-to-motion-3.0",
        "model_version": "text-to-motion-3.0",
        "billing_unit": "second",
        "quantity": 5.0,
        "unit_price": "0.0500",
        "ref": "motion:m1",
        "job_id": "m1",
        "task_id": "J1",
        "status": "ok",
    },
    {
        "id": "pl4",
        "created": "2026-11-03T09:00:00Z",
        "type": "debit",
        "total_usd": "0",
        "balance_before": "10.0000",
        "balance_after": "10.0000",
        "model": "video-to-motion-2.1",
        "ref": "job_failed:J0",
        "task_id": "J0",
        "status": "failed",
    },
    {
        "id": "pl3",
        "created": "2026-11-02T09:00:00Z",
        "type": "topup",
        "total_usd": "10.0000",
        "balance_before": "0.0000",
        "balance_after": "10.0000",
        "ref": "ar:pi_123",
        "status": "paid",
    },
    {
        "id": "pl2",
        "created": "2026-11-01T09:00:00Z",
        "type": "adjustment",
        "total_usd": "-1.0000",
        "balance_before": "1.0000",
        "balance_after": "0.0000",
    },
    {
        "id": "pl1",
        "created": "2026-11-01T08:00:00Z",
        "type": "credit_grant",
        "total_usd": "1.0000",
        "balance_before": "0.0000",
        "balance_after": "1.0000",
        "ref": "aff:pi_9",
    },
]


def test_entries_are_labeled_signed_and_linked():
    request = ledger_request(limit=10)
    page = billing_history_page(ROWS, limit=10, domain="uthana.com", request=request)
    charge, failed, payment, adjustment, grant = page["entries"]
    assert charge["kind"] == "charge" and charge["amount_usd"] == "-0.2500"
    assert charge["motion_id"] == "m1" and charge["character_id"] is None and charge["job_id"] == "J1"
    assert charge["asset_type"] == "motion" and charge["asset_id"] == "m1"
    assert charge["unit_price_usd"] == "0.0500" and charge["billing_unit"] == "second"
    assert failed["is_failed_generation"] is True and failed["amount_usd"] == "0"
    assert failed["motion_id"] is None and failed["asset_id"] is None and failed["job_id"] == "J0"
    assert payment["kind"] == "payment" and payment["payment_source"] == "auto_top_up"
    assert payment["amount_usd"] == "10.0000"
    assert adjustment["kind"] == "adjustment" and adjustment["amount_usd"] == "-1.0000"
    assert grant["kind"] == "free_credit" and grant["is_affiliate_commission"] is True
    assert page["page_totals_usd"] == {
        "charges": "-0.2500",
        "payments": "10.0000",
        "free_credit": "1.0000",
        "adjustments": "-1.0000",
        "other": "0",
    }
    assert page["failed_generations"] == 1 and page["has_more"] is False
    assert page["next_before_entry_id"] is None
    assert page["account_page_url"] == "https://uthana.com/app/account/transactions"
    assert page["currency"] == "USD" and any("legacy monthly plan" in n for n in page["notes"])


def test_paging_reports_the_cursor_and_trims_the_probe_row():
    request = ledger_request(limit=2)
    assert request == {"limit": 3}
    page = billing_history_page(ROWS[:3], limit=2, domain="staging.uthana.com", request=request)
    assert [e["entry_id"] for e in page["entries"]] == ["pl5", "pl4"]
    assert page["has_more"] is True and page["next_before_entry_id"] == "pl4"


def test_unknown_types_are_kept_as_other():
    row = {**ROWS[0], "id": "pl9", "type": "hold"}
    entry = billing_history_page([row], limit=5, domain="uthana.com", request={"limit": 6})["entries"][0]
    assert entry["kind"] == "other" and entry["backend_type"] == "hold" and entry["amount_usd"] == "0.2500"


def test_request_validation_and_mapping():
    request = ledger_request(
        since="2026-11-01", until="2026-11-04T00:00:00Z", entry_types=["charge", "payment"], before_entry_id="pl9"
    )
    assert request == {
        "limit": 51,
        "since": "2026-11-01T00:00:00+00:00",
        "until": "2026-11-04T00:00:00+00:00",
        "types": ["debit", "topup"],
        "before_id": "pl9",
    }
    for kwargs in (
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"since": "last week"},
        {"since": "2026-11-04", "until": "2026-11-01"},
        {"entry_types": []},
        {"entry_types": ["refund"]},
    ):
        with pytest.raises(ValueError):
            ledger_request(**kwargs)


@pytest.mark.parametrize(
    "rows",
    [None, [{"id": "pl1"}], [{**ROWS[0], "total_usd": "NaN"}], [{**ROWS[0], "total_usd": None}]],
)
def test_malformed_backend_rows_are_errors(rows):
    with pytest.raises(APIError):
        billing_history_page(rows, limit=5, domain="uthana.com", request={"limit": 6})


async def test_operation_passes_filters_to_the_client(tmp_path):
    api = FakeAPI()
    seen = {}

    async def ledger(**kwargs):
        seen.update(kwargs)
        return ROWS[:2]

    api.ledger = ledger
    page = await Operations(api, tmp_path).billing_history(entry_types=["charge"], limit=1)
    assert seen == {"limit": 2, "types": ["debit"]}
    assert page["has_more"] is True and page["filters"]["entry_types"] == ["charge"]


def _charge(**fields):
    row = {**ROWS[0], **fields}
    return billing_history_page([row], limit=5, domain="uthana.com", request={"limit": 6})["entries"][0]


def test_motion_debit_reports_the_job_from_task_id_not_the_motion():
    # A real debit row: the backend puts the motion in job_id and the processing job in task_id.
    entry = _charge(job_id="mMotion7Kq2", task_id="J4s8XkP2aQ1", ref="motion:mMotion7Kq2")
    assert entry["job_id"] == "J4s8XkP2aQ1"
    assert entry["asset_type"] == "motion" and entry["asset_id"] == "mMotion7Kq2"
    assert entry["motion_id"] == "mMotion7Kq2" and entry["character_id"] is None


def test_character_debit_without_a_worker_job_has_no_job_id():
    entry = _charge(job_id="cChar9", task_id=None, ref="character:cChar9")
    assert entry["job_id"] is None
    assert entry["asset_type"] == "character" and entry["character_id"] == "cChar9" and entry["motion_id"] is None


def test_failed_generation_job_falls_back_to_the_ref():
    entry = _charge(job_id=None, task_id=None, ref="job_failed:J0Failed", status="failed", total_usd="0")
    assert entry["job_id"] == "J0Failed" and entry["asset_id"] is None and entry["is_failed_generation"] is True


def test_asset_id_without_a_known_ref_is_never_reported_as_a_job():
    entry = _charge(job_id="mMotion7Kq2", task_id=None, ref="legacy:abc")
    assert entry["job_id"] is None
    assert entry["asset_id"] == "mMotion7Kq2" and entry["asset_type"] is None
    assert entry["motion_id"] is None and entry["character_id"] is None
