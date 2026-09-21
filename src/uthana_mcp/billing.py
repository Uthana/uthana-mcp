"""Published-capability pricing policy; no separate API/MCP or agent-token fee."""

from decimal import Decimal, InvalidOperation

from .api import APIError
from .validation import number

PRICING_URL = "https://uthana.com/pricing"
# Public names -> backend rate keys. Reviewed against the pricing page 2026-09-14.
# Rates themselves are fetched, never hardcoded here. Hidden backend SKUs are not public prices.
PUBLISHED_MODELS = {
    "text-to-motion-1.0": "text-to-motion",
    "text-to-motion-2.0": "text-to-motion-bucmd",
    "text-to-motion-3.0": "text-to-motion-3.0",
    "video-to-motion-2.0": "video-to-motion-2.0",
    "video-to-motion-2.1": "video-to-motion-2.1",
    "locomotion-1.0": "locomotion",
    "stitch-loop-2.0": "stitch-loop",
    "autorig": "autorig",
    "character-gen-1.0": "character-gen-1.0",
}


def estimate_cost(rates, model, quantity):
    if model not in PUBLISHED_MODELS:
        raise ValueError("model must be one of: " + ", ".join(PUBLISHED_MODELS))
    quantity = number(quantity, 0, 3600)
    if quantity == 0:
        raise ValueError("quantity must be positive")
    key = PUBLISHED_MODELS[model]
    expected_unit = "rig" if model == "autorig" else "character" if model == "character-gen-1.0" else "second"
    if expected_unit != "second" and quantity != int(quantity):
        raise ValueError("Rig and character quantities must be whole numbers")
    matches = [r for r in rates if r.get("model_key") == key] if isinstance(rates, list) else []
    if len(matches) != 1 or matches[0].get("billing_unit") != expected_unit:
        raise APIError("Published model rate is unavailable or ambiguous; do not assume zero")
    try:
        rate = Decimal(str(matches[0]["unit_price"]))
    except (KeyError, InvalidOperation):
        raise APIError("Invalid published model rate") from None
    if not rate.is_finite() or rate < 0:
        raise APIError("Invalid published model rate")
    return {
        "model": model,
        "quantity": quantity,
        "billing_unit": expected_unit,
        "unit_price_usd": str(rate),
        "estimated_cost_usd": str((rate * Decimal(str(quantity))).quantize(Decimal("0.0001"))),
        "actual_cost_usd": None,
        "status": "estimate",
        "api_mcp_fee_usd": "0",
        "agent_token_fee_usd": "0",
        "pricing_url": PRICING_URL,
        "rate_source": "configured Uthana environment: GraphQL payg_prices",
        "note": "Estimate for the supplied output quantity, not a measured debit. Public capability mapping was "
        "checked against the pricing page on 2026-09-14. Reconcile any rate mismatch with that page; "
        "never invent a credits-to-USD conversion. Actual generated duration and account terms may differ.",
    }


def receipt_billing(operation, args):
    model = {
        "generate": "text-to-motion-3.0",
        "generate_v2": "text-to-motion-2.0",
        "locomotion": "locomotion-1.0",
        "video": args.get("model"),
        "character_from_image": "character-gen-1.0",
        "loop": "stitch-loop-2.0",
        "stitch": "stitch-loop-2.0",
    }.get(operation)
    if operation == "upload_character" and args.get("auto_rig") is True:
        model = "autorig"
    # Skeleton conversion (rerig_target) has no published price entry; do not assert it is free.
    free = operation in {"trim", "save", "download", "preview"} or (
        operation == "upload_character" and args.get("auto_rig") is False and not args.get("rerig_target")
    )
    return {
        "api_mcp_fee_usd": "0",
        "agent_token_fee_usd": "0",
        "pricing_url": PRICING_URL,
        "model": model,
        "cost_status": "free_by_policy" if free else "unmeasured",
        "actual_cost_usd": "0" if free else None,
        "note": "Published capabilities retain their prices; unlisted platform operations are free. "
        "This does not remove backend access or legacy account limits.",
    }
