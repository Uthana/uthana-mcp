"""Read-only catalog and usage interpretation, independent of the MCP transport."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field
from uthana.types import AssetOrder, AssetSource

from .api import APIError
from .billing import PRICING_URL, PUBLISHED_MODELS
from .validation import identifier, number

MAX_PAGE_SIZE = 100
MAX_CURSOR_LENGTH = 8192


class AssetBrowseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(default="", max_length=200)
    source: AssetSource = "all"
    order: AssetOrder = "created_desc"
    limit: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    cursor: str | None = Field(default=None, min_length=1, max_length=MAX_CURSOR_LENGTH)


class MotionBrowseInput(AssetBrowseInput):
    method: str | None = Field(default=None, min_length=1, max_length=100)


class AssetSummary(TypedDict):
    name: str | None
    created: str | None
    updated: str | None
    org_id: str | None
    character_id: NotRequired[str]
    motion_id: NotRequired[str]
    method: NotRequired[str | None]


def asset_page(data: object, *, kind: Literal["character", "motion"], limit: int) -> dict[str, object]:
    """Validate one SDK page without filtering, sorting or changing its continuation cursor."""
    message = f"Uthana returned an invalid {kind} page. Retry the read or contact Uthana support."
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or "next_cursor" not in data:
        raise APIError(message, outcome="not_applicable")
    rows = data["items"]
    cursor = data["next_cursor"]
    if (
        len(rows) > limit
        or cursor is not None
        and (not isinstance(cursor, str) or not cursor or len(cursor) > MAX_CURSOR_LENGTH)
    ):
        raise APIError(message, outcome="not_applicable")
    items: list[AssetSummary] = []
    for row in rows:
        if not isinstance(row, dict):
            raise APIError(message, outcome="not_applicable")
        try:
            asset_id = identifier(row.get("id"))
            org_id = identifier(row["org_id"]) if row.get("org_id") is not None else None
        except ValueError:
            raise APIError(message, outcome="not_applicable") from None
        name, created, updated = row.get("name"), row.get("created"), row.get("updated")
        if any(value is not None and not isinstance(value, str) for value in (name, created, updated)):
            raise APIError(message, outcome="not_applicable")
        item: AssetSummary = {"name": name, "created": created, "updated": updated, "org_id": org_id}
        if kind == "character":
            item["character_id"] = asset_id
        else:
            item["motion_id"] = asset_id
            tags = row.get("tags")
            method = tags.get("Method") if isinstance(tags, dict) else None
            item["method"] = method if isinstance(method, str) else None
        items.append(item)
    return {kind + "s": items, "next_cursor": cursor}


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
    subscription = data.get("subscription")
    if subscription is None:
        subscription = {}
    if not isinstance(subscription, dict):
        raise APIError("Invalid subscription in usage response")
    subscription_status = subscription.get("status")
    if subscription_status is not None and not isinstance(subscription_status, str):
        raise APIError("Invalid subscription status in usage response")
    org_name = org.get("name")
    if org_name is not None and not isinstance(org_name, str):
        raise APIError("Invalid organization name in usage response")
    active = subscription_status == "active"
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
        "organization": {"id": identifier(org["id"]) if org.get("id") is not None else None, "name": org_name},
        "subscription": {
            "status": subscription_status,
            "download_seconds_per_month": optional_number(subscription.get("secs_per_month")),
            "characters": optional_number(subscription.get("characters")),
        },
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
