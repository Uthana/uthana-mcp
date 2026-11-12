"""Read-only capability catalog: what Uthana offers, what this MCP deployment exposes, and account eligibility.

The catalog is reviewed data, not a live probe of the platform. It never creates work or charges.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import NotRequired, TypedDict

from .billing import PRICING_URL, PUBLISHED_MODELS


class Capability(TypedDict):
    id: str
    name: str
    status: str
    summary: str
    tools: list[str]
    models: list[str]
    limits: list[str]
    access: str | None
    docs: str | None
    available_here: NotRequired[bool]


REVIEWED = "2026-11-11"
DOCS = "https://uthana.com/docs/api"

# available: callable through a tool in this package (check deployment.tools for this server).
# platform_only: offered by Uthana in the web app or API, intentionally not an MCP tool.
# planned: tracked for a future MCP release; not callable here.
# not_offered: not a customer platform function for this MCP.
STATUSES = ("available", "platform_only", "planned", "not_offered")


def _op(
    id: str,
    name: str,
    *,
    status: str,
    summary: str,
    tools: Sequence[str] = (),
    models: Sequence[str] = (),
    limits: Sequence[str] = (),
    docs: str | None = None,
    access: str | None = None,
) -> Capability:
    return {
        "id": id,
        "name": name,
        "status": status,
        "summary": summary,
        "tools": list(tools),
        "models": list(models),
        "limits": list(limits),
        "access": access,
        "docs": docs,
    }


WRITE = "Creates or changes account data; hosted connections need the mcp:write scope."
READ = "Read-only."
PRICED = WRITE + " Priced; check estimate_model_cost before large requests."

OPERATIONS = [
    _op(
        "discovery",
        "Capability discovery",
        status="available",
        summary="This catalog: operations, models, limits, this deployment's tools, and account eligibility.",
        tools=["get_capabilities"],
        access=READ,
    ),
    _op(
        "text_to_motion_3",
        "Text-to-motion 3.0: Regular, Lite and Mini",
        status="available",
        tools=["generate_motion", "get_job"],
        docs=f"{DOCS}/capabilities/text-to-motion",
        access=PRICED,
        summary="Choose Regular, Lite or Mini with an independent fast hint. Regular includes finger animation. Returns a job.",
        models=["text-to-motion-3.0", "text-to-motion-3.0-lite", "text-to-motion-3.0-mini"],
        limits=[
            "Backend rounds and clamps duration: Regular 4-10 seconds; Lite/Mini 5-10 seconds",
            "Prompt up to 1000 characters",
        ],
    ),
    _op(
        "text_to_motion_2",
        "Text-to-motion 2.0 (TTM V2)",
        status="available",
        summary="Fast basic motion for placeholders and previz. No finger animation. Returns a motion directly.",
        tools=["generate_motion_v2"],
        models=["text-to-motion-2.0"],
        limits=["4-10 seconds in 0.4-second steps", "Prompt up to 1000 characters", "Inference around 5 seconds"],
        docs=f"{DOCS}/capabilities/text-to-motion",
        access=PRICED,
    ),
    _op(
        "text_to_motion_1",
        "Text-to-motion 1.0 (TTM V1)",
        status="platform_only",
        summary="Offered in the web app and as the API's default text-to-motion model. Not an MCP tool by design; use V2 for fast basic motion or V3 for quality. Its price entry does not make it callable here.",
        models=["text-to-motion-1.0"],
        docs=f"{DOCS}/capabilities/text-to-motion",
    ),
    _op(
        "video_to_motion",
        "Video-to-motion 2.0 / 2.1 / 3.0",
        status="available",
        tools=["generate_motion_from_video", "get_job"],
        limits=["MP4, MOV or WebM", "Up to 128 MiB"],
        docs=f"{DOCS}/capabilities/video-to-motion",
        access=PRICED,
        summary="Motion capture from a selected video; 3.0 by default, 2.0 or 2.1 on request. Returns a job.",
        models=["video-to-motion-2.0", "video-to-motion-2.1", "video-to-motion-3.0"],
    ),
    _op(
        "locomotion",
        "Locomotion cycles",
        status="available",
        summary="Loopable walk and run cycles in a chosen style, speed and direction.",
        tools=["list_locomotion_styles", "generate_locomotion"],
        models=["locomotion-1.0"],
        limits=["1-5 stride pairs; duration follows strides", "0.25-8 m/s on the UE5 reference mannequin"],
        docs=f"{DOCS}/capabilities/locomotion",
        access=PRICED,
    ),
    _op(
        "controlled_locomotion",
        "Path-controlled locomotion",
        status="planned",
        summary="Locomotion that follows a supplied path or steering input. Not available in this release.",
    ),
    _op(
        "loop",
        "Loop an existing motion",
        status="available",
        summary="Make a motion loop cleanly.",
        tools=["create_looped_motion"],
        models=["stitch-loop-2.0"],
        docs=f"{DOCS}/capabilities/stitch-loop-motions",
        access=PRICED,
    ),
    _op(
        "stitch",
        "Stitch motions with a generated transition",
        status="available",
        summary="Join motion, transition and motion steps with server-side pose sampling and alignment.",
        tools=["stitch"],
        models=["stitch-loop-2.0"],
        docs=f"{DOCS}/capabilities/stitching-sampled-poses",
        access=PRICED,
    ),
    _op(
        "trim_and_save",
        "Trim a motion or save an edited GLTF",
        status="available",
        summary="Native trim, and registration of a host-edited GLTF as a new motion. Free.",
        tools=["trim_motion", "save_motion"],
        access=WRITE,
    ),
    _op(
        "upload_character",
        "Upload a character, auto-rig, re-rig",
        status="available",
        summary="Add an FBX or GLB character; optionally auto-rig, include fingers, face forward, or convert to r15/ue5.",
        tools=["upload_character"],
        models=["autorig"],
        limits=[
            "FBX or GLB",
            "Up to 30 MiB",
            "Auto-rigging a mesh without a rig is priced; uploading a rigged character, including re-rigging its skeleton, is free",
        ],
        docs=f"{DOCS}/capabilities/auto-rig-and-upload-character",
        access=WRITE,
    ),
    _op(
        "character_from_image_or_prompt",
        "Create a character from an image or a text prompt",
        status="available",
        summary="Generate a rigged character from one image, or preview prompt images and finalize one.",
        tools=["create_character_from_image", "preview_character_from_prompt", "create_character_from_prompt"],
        models=["character-gen-1.0"],
        limits=["PNG or JPEG, up to 16 MiB and 16 megapixels", "A prompt preview can be finalized once"],
        docs=f"{DOCS}/capabilities/auto-rig-and-add-character",
        access=PRICED,
    ),
    _op(
        "find_assets",
        "List characters and recent motions",
        status="available",
        summary="Name filters over the account's characters and up to 1000 recent organization motions plus examples.",
        tools=["list_characters", "list_motions", "get_motion"],
        limits=["Not a full or semantic library search", "Character catalog read is capped at 16 MiB"],
        docs=f"{DOCS}/capabilities/asset-management",
        access=READ,
    ),
    _op(
        "library_search",
        "Copy the best library motion",
        status="available",
        summary="Charged semantic search over the shared library and organization clips. Copies one best match; a weak match is still charged.",
        tools=["copy_best_library_motion"],
        models=["library-search-1.0"],
        limits=["One result; no candidate list, library browsing, pagination or similarity-to-motion search"],
        access=PRICED,
    ),
    _op(
        "manage_assets",
        "Rename, delete and restore assets",
        docs=f"{DOCS}/capabilities/asset-management",
        status="available",
        summary="Manage assets using your account's permissions. Delete selects only by ID; soft deletion is restorable.",
        tools=[
            "rename_character",
            "rename_motion",
            "delete_character",
            "delete_motion",
            "restore_character",
            "restore_motion",
        ],
        access=WRITE,
    ),
    _op(
        "inspect",
        "Preview and inspect motions",
        status="available",
        summary="Metadata, APNG/WebM previews and decoded preview frames. Free.",
        tools=["get_motion", "get_preview", "get_preview_frame"],
        access=READ,
    ),
    _op(
        "export_motion",
        "Export a motion on a character",
        status="available",
        summary="Retargeted FBX, GLB or BVH with frame rate, mesh, in-place, Roblox, speed and torso options.",
        tools=["check_download_allowed", "download_motion"],
        limits=["24, 30 or 60 fps", "Speed multiplier above 0 and at most 2"],
        docs=f"{DOCS}/capabilities/downloading-motion",
        access="Counts against monthly download seconds on legacy plans; free on pay-as-you-go. Hosted connections need the mcp:write scope.",
    ),
    _op(
        "hosted_artifacts",
        "Re-download a hosted export",
        status="available",
        summary="Hosted connections only: fetch a fresh link for an export already made, without exporting or charging again.",
        tools=["get_artifact_download"],
        access=READ,
    ),
    _op(
        "export_other_formats",
        "Robot joint trajectories (Unitree G1) and USD/USDZ export",
        status="planned",
        summary="Not available in this release.",
        docs=f"{DOCS}/capabilities/unitree-g1",
    ),
    _op(
        "download_character",
        "Download a character file",
        docs=f"{DOCS}/capabilities/downloading-character",
        status="available",
        summary="Download a character's own GLB or FBX model without animation. Free.",
        tools=["download_character"],
        access=READ,
    ),
    _op(
        "share_links",
        "Public share links for motions",
        status="planned",
        summary="Not available in this release. Owners can view motions in the Uthana web app.",
    ),
    _op(
        "batch",
        "Batch generation, retargeting and export",
        status="planned",
        summary="Not available in this release; call the single-item tools per item.",
    ),
    _op(
        "realtime",
        "Real-time character control",
        status="planned",
        summary="Experimental streaming control; not a published API capability and not available in this release.",
    ),
    _op(
        "usage_and_pricing",
        "Balance, rates, allowances and estimates",
        status="available",
        summary="Read pay-as-you-go balance and rates, monthly allowances, and estimate a model cost. Never creates work.",
        tools=["get_usage", "estimate_model_cost"],
        docs=f"{DOCS}/pricing",
        access=READ,
    ),
    _op(
        "recovery",
        "Jobs and request recovery",
        status="available",
        summary="Poll a job and read the local receipt for an interrupted request.",
        tools=["get_job", "get_request_status"],
        access=READ,
    ),
    _op(
        "billing_history",
        "Read billing history",
        docs=f"{DOCS}/pricing",
        status="available",
        summary="Read recorded PAYG charges, payments, free credit and adjustments with paging and time/type filters.",
        tools=["get_billing_history"],
        access=READ,
    ),
    _op(
        "account_admin",
        "Profile, API keys and plan changes",
        status="not_offered",
        summary="Account security and plan administration stay in the Uthana web app.",
        docs=f"{DOCS}/capabilities/account-and-organization",
    ),
    _op(
        "editor_control",
        "Scene, pose and editor control (Blender, Unreal, Maya)",
        status="not_offered",
        summary="Host-editor work, not an Uthana platform function. Export from Uthana, then edit with the host's tools.",
    ),
    _op(
        "raw_api",
        "Arbitrary GraphQL execution",
        status="not_offered",
        summary="This MCP maps documented operations to typed tools; it does not run raw API mutations.",
        docs=f"{DOCS}/graphql",
    ),
]

OPERATIONS.extend(
    [
        _op(
            "library_browsing",
            "Library browsing and similarity-to-motion search",
            status="planned",
            summary="Candidate browsing, pagination and searching from a reference motion are not tools in this release.",
        ),
        _op(
            "billing_actions",
            "Purchases, top-ups and billing changes",
            status="planned",
            summary="Use the Uthana account page. Billing history does not authorize or perform financial changes.",
        ),
    ]
)

NOTES = [
    "Discovery is read-only: it never submits generation, export or billing work.",
    "status=available means this package has a tool for it; deployment.tools lists what this server registered.",
    "Platform support, this deployment's tools, and the account's eligibility are separate questions. "
    "A listed price never makes an operation callable here.",
    "Rates come from the configured environment at call time (get_usage, estimate_model_cost); "
    "they are not hardcoded here. Published prices: " + PRICING_URL,
]


def catalog(*, version: str, domain: str, transport: str, tools: Iterable[str]) -> dict[str, object]:
    """Static catalog plus facts about this server; no network calls."""
    registered = sorted(tools)
    operations: list[Capability] = []
    for row in OPERATIONS:
        entry = row.copy()
        if row["status"] == "available":
            entry["available_here"] = all(tool in registered for tool in row["tools"])
        operations.append(entry)
    return {
        "schema_version": 1,
        "reviewed": REVIEWED,
        "statuses": list(STATUSES),
        "deployment": {
            "package": "uthana-mcp",
            "version": version,
            "environment": domain,
            "transport": transport,
            "tools": registered,
        },
        "operations": operations,
        "pricing_url": PRICING_URL,
        "documentation": DOCS,
        "notes": NOTES,
    }


def account_eligibility(usage: object) -> dict[str, object]:
    """Summarize which priced models this account can currently use, from a usage_snapshot result."""
    if not isinstance(usage, dict):
        raise ValueError("Expected an account usage snapshot")
    payg = usage.get("payg")
    if payg is None:
        payg = {}
    if not isinstance(payg, dict):
        raise ValueError("Expected PAYG account information")
    rates = payg.get("rates")
    priced = {row["model"]: row for row in rates} if isinstance(rates, list) else None
    models = {}
    for model in PUBLISHED_MODELS:
        if priced is None:
            models[model] = {"rate_listed": None}
        else:
            row = priced.get(model)
            models[model] = {
                "rate_listed": row is not None,
                "unit_price_usd": row["unit_price_usd"] if row else None,
                "billing_unit": row["billing_unit"] if row else None,
            }
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "payg_enabled": usage.get("payg_enabled"),
        "payg_balance_usd": payg.get("balance_usd"),
        "monthly_downloads": usage.get("monthly_downloads"),
        "monthly_characters": usage.get("monthly_characters"),
        "models": models,
        "note": "rate_listed=false means the environment returned no rate for this account; null means unknown. "
        "Neither is a permission check: the backend decides each request. Use check_download_allowed for exports.",
    }
