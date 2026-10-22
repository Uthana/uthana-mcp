"""Read-only catalog and usage interpretation, independent of the MCP transport."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .api import APIError
from .billing import PRICING_URL, PUBLISHED_MODELS
from .validation import identifier, number


def page_bounds(offset, limit):
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be 1–100")


def catalog_filters(query, source, method, offset, limit):
    page_bounds(offset, limit)
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("query must be at most 200 characters")
    if source not in {"available", "organization", "examples"}:
        raise ValueError("source must be available, organization, or examples")
    if method is not None and (not isinstance(method, str) or not method.strip() or len(method) > 100):
        raise ValueError("method must be a nonempty method name of at most 100 characters")


def motion_page(data, query, source, method, offset, limit):
    org = data.get("org")
    rows = data.get("motions")
    if not isinstance(org, dict) or not org.get("id") or not isinstance(rows, list):
        raise APIError("Motion catalog or organization unavailable")
    org_id = identifier(org["id"])
    tokens = query.casefold().split()
    results, seen = [], set()
    organization_count = 0
    for row in rows:
        motion_id = identifier(row["id"])
        if motion_id in seen:
            continue
        seen.add(motion_id)
        is_own = identifier(row["org_id"]) == org_id
        organization_count += int(is_own)
        name = row.get("name")
        if not isinstance(name, str):
            raise APIError("Motion catalog returned an invalid name")
        tags = row.get("tags") or {}
        method_name = tags.get("Method") if isinstance(tags, dict) else None
        if not isinstance(method_name, str):
            method_name = None
        if source == "organization" and not is_own:
            continue
        if source == "examples" and is_own:
            continue
        if method is not None and (method_name or "").casefold() != method.strip().casefold():
            continue
        if not all(token in name.casefold() for token in tokens):
            continue
        results.append(
            {
                "motion_id": motion_id,
                "name": name,
                "created": row.get("created"),
                "method": method_name,
                "source": "organization" if is_own else "uthana_example",
            }
        )
    return {
        "motions": results[offset : offset + limit],
        "next_offset": offset + limit if offset + limit < len(results) else None,
        "matched_in_available_window": len(results),
        "scanned_count": len(seen),
        "query": query,
        "source": source,
        "method": method,
        "search_kind": "case_insensitive_name_tokens",
        "organization_window_may_be_truncated": organization_count >= 1000,
        "full_library_searched": False,
        "scope_note": "Up to 1000 recent organization motions plus examples supplied by the API. "
        "No semantic search, full shared-library search, or older-history pagination. "
        "Offsets page this filtered window; concurrent library changes may move results.",
    }


def optional_number(value):
    return None if value is None else number(value, 0, 1e15)


def usd(value):
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise APIError("Invalid USD amount in usage response") from None
    if not amount.is_finite():
        raise APIError("Invalid USD amount in usage response")
    return str(amount)


def usage_snapshot(data):
    org = data.get("org")
    if not isinstance(org, dict):
        raise APIError("Organization usage unavailable")
    payg = org.get("payg_enabled")
    if payg is not None and not isinstance(payg, bool):
        raise APIError("Invalid billing mode in usage response")
    subscription = data.get("subscription") or {}
    active = subscription.get("status") == "active"
    download_limit = optional_number(
        subscription.get("secs_per_month") if active else org.get("motion_download_secs_per_month")
    )
    character_limit = optional_number(org.get("characters_allowed"))
    if active:
        plan_characters = optional_number(subscription.get("characters"))
        character_limit = (
            max(character_limit, plan_characters) if None not in (character_limit, plan_characters) else None
        )
    applicable = False if payg is True else True if payg is False else None
    prices = data.get("payg_prices")
    if prices is not None and not isinstance(prices, list):
        raise APIError("Invalid PAYG rates response")
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "organization",
        "pricing_url": PRICING_URL,
        "api_mcp_fee_usd": "0",
        "agent_token_fee_usd": "0",
        "pricing_policy": "Published capabilities have their listed prices; unlisted platform operations are free.",
        "payg_enabled": payg,
        "payg": {
            "balance_usd": usd(org.get("payg_total_usd")),
            "auto_recharge_enabled": org.get("payg_auto_recharge_enabled"),
            "rates": (
                None
                if prices is None
                else [
                    {
                        "model_key": row["model_key"],
                        "model": next(k for k, v in PUBLISHED_MODELS.items() if v == row["model_key"]),
                        "billing_unit": row["billing_unit"],
                        "unit_price_usd": usd(row["unit_price"]),
                    }
                    for row in prices
                    if row.get("model_key") in PUBLISHED_MODELS.values()
                ]
            ),
        },
        "monthly_downloads": {
            "unit": "motion_seconds",
            "quota_applies_to_billing_mode": applicable,
            "limit": download_limit if applicable else None,
            "remaining": optional_number(org.get("motion_download_secs_per_month_remaining")) if applicable else None,
        },
        "monthly_characters": {
            "unit": "characters",
            "quota_applies_to_billing_mode": applicable,
            "limit": character_limit if applicable else None,
            "remaining": optional_number(org.get("characters_allowed_remaining")) if applicable else None,
        },
        "operation_cost_known": False,
        "notes": [
            "USD balances/rates and monthly quotas are separate; null means unavailable or not applicable, never zero.",
            "PAYG currently meters generation and has no monthly download/character cap; auto-rig can still charge.",
            "This snapshot is not a quote, spending reservation, or permission to act. Rates do not establish a job's final cost.",
            "Role exemptions and previous downloads can allow a specific export despite exhausted monthly seconds. "
            "Use check_download_allowed for that motion and character; the download endpoint remains authoritative.",
        ],
    }
