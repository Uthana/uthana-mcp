"""Read-only PAYG billing history: label backend ledger rows for reconciliation."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .api import APIError

ENTRY_TYPES = {
    "charge": "debit",
    "payment": "topup",
    "free_credit": "credit_grant",
    "adjustment": "adjustment",
}
KINDS = {backend: kind for kind, backend in ENTRY_TYPES.items()}
LABELS = {
    "charge": "Charge for a generation or other paid operation",
    "payment": "Card or invoice payment added to purchased balance",
    "free_credit": "Free credit added by Uthana (welcome, promotion or affiliate commission)",
    "adjustment": "Balance correction made by Uthana staff",
}
ASSET_TYPES = ("motion", "character")
PAYMENT_SOURCES = {"pi": "checkout", "inv": "invoice", "ar": "auto_top_up"}
MAX_PAGE = 100
NOTES = [
    "Amounts are recorded USD ledger entries, not estimates. Estimates from estimate_model_cost are never stored here.",
    "amount_usd is signed: charges are negative, payments and free credit positive, adjustments either way.",
    "balance_before_usd and balance_after_usd are the total spendable balance (free credit plus purchased balance). Charges use free credit first.",
    "On a charge, asset_id (with motion_id or character_id) is the motion or character that was charged; job_id is the processing job, for get_job. Either can be null, for example a failed generation has no asset.",
    "A failed generation is recorded as a $0 charge with status failed; nothing is taken, so there is no separate refund entry. Uthana records no refund entry type.",
    "Organizations on a legacy monthly plan are not billed per operation and have no entries; use get_usage for remaining monthly allowances.",
    "Invoices and receipts are not available through the MCP. A signed-in member can open them from the account page's Invoices button.",
    "This history is read-only and is not permission to buy credit or change billing settings.",
]


def parse_time(name, value):
    """Validate an ISO 8601 timestamp; naive values are UTC. Returns (datetime, original string)."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} must be an ISO 8601 timestamp such as 2026-11-01T00:00:00Z.") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def ledger_request(since=None, until=None, entry_types=None, before_entry_id=None, limit=50):
    """Validate tool arguments and return client keyword arguments (asking for one extra row)."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE:
        raise ValueError(f"limit must be an integer from 1 to {MAX_PAGE}.")
    start, end = parse_time("since", since), parse_time("until", until)
    if start and end and start >= end:
        raise ValueError("since must be earlier than until.")
    types = None
    if entry_types is not None:
        unknown = [t for t in entry_types if t not in ENTRY_TYPES]
        if unknown or not entry_types:
            raise ValueError(f"entry_types must be a non-empty list from {sorted(ENTRY_TYPES)}.")
        types = sorted({ENTRY_TYPES[t] for t in entry_types})
    request = {"limit": limit + 1}
    for key, value in (
        ("since", start.isoformat() if start else None),
        ("until", end.isoformat() if end else None),
        ("types", types),
        ("before_id", before_entry_id),
    ):
        if value is not None:
            request[key] = value
    return request


def _amount(value, field):
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise APIError(f"Invalid {field} in billing history response") from None
    if not amount.is_finite():
        raise APIError(f"Invalid {field} in billing history response")
    return amount


def _text(value):
    return value if isinstance(value, str) and value else None


def charge_references(row, prefix, value):
    """Split a debit row into the charged asset and the processing job.

    The backend stores the charged motion or character ID in ``job_id`` and the
    processing job in ``task_id``; ``ref`` is ``motion:<id>``, ``character:<id>``
    or, for a failed generation, ``job_failed:<job id>``.
    """
    asset_type = prefix if prefix in ASSET_TYPES and value else None
    asset_id = value if asset_type else _text(row.get("job_id"))
    job_id = _text(row.get("task_id")) or (value if prefix == "job_failed" and value else None)
    return {
        "asset_type": asset_type,
        "asset_id": asset_id,
        "motion_id": asset_id if asset_type == "motion" else None,
        "character_id": asset_id if asset_type == "character" else None,
        "job_id": job_id,
    }


def ledger_entry(row):
    if not isinstance(row, dict) or not _text(row.get("id")) or not _text(row.get("type")):
        raise APIError("Invalid billing history response")
    backend_type = row["type"]
    kind = KINDS.get(backend_type, "other")
    total = _amount(row.get("total_usd"), "amount")
    if total is None:
        raise APIError("Invalid amount in billing history response")
    signed = -abs(total) if kind == "charge" else total
    ref = _text(row.get("ref")) or ""
    prefix, _, value = ref.partition(":")
    entry = {
        "entry_id": row["id"],
        "recorded_at": row.get("created"),
        "kind": kind,
        "label": LABELS.get(kind, f"Other ledger entry ({backend_type})"),
        "amount_usd": str(signed),
        "balance_before_usd": str(_amount(row.get("balance_before"), "balance")),
        "balance_after_usd": str(_amount(row.get("balance_after"), "balance")),
        "status": _text(row.get("status")),
    }
    if kind == "other":
        entry["backend_type"] = backend_type
    if kind == "charge":
        unit_price = _amount(row.get("unit_price"), "unit price")
        entry.update(
            {
                "is_failed_generation": row.get("status") == "failed",
                "model": _text(row.get("model")),
                "model_version": _text(row.get("model_version")),
                "billing_unit": _text(row.get("billing_unit")),
                "quantity": row.get("quantity"),
                "unit_price_usd": None if unit_price is None else str(unit_price),
                **charge_references(row, prefix, value),
            }
        )
    elif kind == "payment":
        entry["payment_source"] = PAYMENT_SOURCES.get(prefix)
        entry["payment_reference"] = ref or None
    elif kind == "free_credit":
        entry["is_affiliate_commission"] = prefix == "aff"
    return entry


def billing_history_page(rows, *, limit, domain, request):
    if not isinstance(rows, list):
        raise APIError("Billing history unavailable")
    has_more = len(rows) > limit
    entries = [ledger_entry(row) for row in rows[:limit]]
    totals = {kind: Decimal("0") for kind in (*ENTRY_TYPES, "other")}
    for entry in entries:
        totals[entry["kind"]] += Decimal(entry["amount_usd"])
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "organization",
        "currency": "USD",
        "filters": {
            "since": request.get("since"),
            "until": request.get("until"),
            "entry_types": sorted(KINDS[t] for t in request["types"]) if request.get("types") else None,
            "before_entry_id": request.get("before_id"),
        },
        "entries": entries,
        "has_more": has_more,
        "next_before_entry_id": entries[-1]["entry_id"] if has_more and entries else None,
        "page_totals_usd": {
            "charges": str(totals["charge"]),
            "payments": str(totals["payment"]),
            "free_credit": str(totals["free_credit"]),
            "adjustments": str(totals["adjustment"]),
            "other": str(totals["other"]),
        },
        "failed_generations": sum(1 for e in entries if e.get("is_failed_generation")),
        "account_page_url": f"https://{domain}/app/account/transactions",
        "notes": NOTES,
    }
