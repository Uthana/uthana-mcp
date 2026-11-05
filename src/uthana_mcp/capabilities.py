"""Read-only capability catalog: what Uthana offers, what this MCP deployment exposes, and account eligibility.

The catalog is reviewed data, not a live probe of the platform. It never creates work or charges.
"""

from datetime import datetime, timezone

from .billing import PRICING_URL, PUBLISHED_MODELS

REVIEWED = "2026-11-04"
DOCS = "https://uthana.com/docs/api"

# available: callable through a tool in this package (check deployment.tools for this server).
# platform_only: offered by Uthana in the web app or API, intentionally not an MCP tool.
# planned: tracked for a future MCP release; not callable here.
# not_offered: not a customer platform function for this MCP.
STATUSES = ("available", "platform_only", "planned", "not_offered")


def _op(id, name, status, summary, *, tools=(), models=(), limits=(), docs=None, access=None):
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
        "available",
        "This catalog: operations, models, limits, this deployment's tools, and account eligibility.",
        tools=["get_capabilities"],
        access=READ,
    ),
    _op(
        "text_to_motion_3",
        "Text-to-motion 3.0 (TTM V3)",
        "available",
        "General, compound, expressive and acrobatic motion with finger animation. Asynchronous job.",
        tools=["generate_motion", "get_job"],
        models=["text-to-motion-3.0"],
        limits=["4-10 seconds, whole seconds", "Prompt up to 1000 characters", "Inference roughly 1-2 minutes"],
        docs=f"{DOCS}/capabilities/text-to-motion",
        access=PRICED,
    ),
    _op(
        "text_to_motion_3_variants",
        "Text-to-motion 3.0 Fast, Lite and Mini",
        "planned",
        "Faster TTM V3 variants. Not selectable in this release; generate_motion uses standard TTM V3.",
        docs=f"{DOCS}/capabilities/text-to-motion",
    ),
    _op(
        "text_to_motion_2",
        "Text-to-motion 2.0 (TTM V2)",
        "available",
        "Fast basic motion for placeholders and previz. No finger animation. Returns a motion directly.",
        tools=["generate_motion_v2"],
        models=["text-to-motion-2.0"],
        limits=["4-10 seconds in 0.4-second steps", "Prompt up to 1000 characters", "Inference around 5 seconds"],
        docs=f"{DOCS}/capabilities/text-to-motion",
        access=PRICED,
    ),
    _op(
        "text_to_motion_1",
        "Text-to-motion 1.0 (TTM V1)",
        "platform_only",
        "Offered in the web app and as the API's default text-to-motion model. Not an MCP tool by design; "
        "use V2 for fast basic motion or V3 for quality. Its price entry does not make it callable here.",
        models=["text-to-motion-1.0"],
        docs=f"{DOCS}/capabilities/text-to-motion",
    ),
    _op(
        "video_to_motion",
        "Video-to-motion 2.0 / 2.1 (V2M)",
        "available",
        "Motion capture from a user-selected video. Asynchronous job.",
        tools=["generate_motion_from_video", "get_job"],
        models=["video-to-motion-2.0", "video-to-motion-2.1"],
        limits=["MP4, MOV or WebM", "Up to 128 MiB"],
        docs=f"{DOCS}/capabilities/video-to-motion",
        access=PRICED,
    ),
    _op(
        "video_to_motion_3",
        "Video-to-motion 3.0 and high-quality hands",
        "planned",
        "Newer video model and hand reconstruction option. Not selectable in this release.",
        docs=f"{DOCS}/capabilities/video-to-motion",
    ),
    _op(
        "locomotion",
        "Locomotion cycles",
        "available",
        "Loopable walk and run cycles in a chosen style, speed and direction.",
        tools=["list_locomotion_styles", "generate_locomotion"],
        models=["locomotion-1.0"],
        limits=["1-5 stride pairs; duration follows strides", "0.25-8 m/s on the UE5 reference mannequin"],
        docs=f"{DOCS}/capabilities/locomotion",
        access=PRICED,
    ),
    _op(
        "controlled_locomotion",
        "Path-controlled locomotion",
        "planned",
        "Locomotion that follows a supplied path or steering input. Not available in this release.",
    ),
    _op(
        "loop",
        "Loop an existing motion",
        "available",
        "Make a motion loop cleanly.",
        tools=["create_looped_motion"],
        models=["stitch-loop-2.0"],
        docs=f"{DOCS}/capabilities/stitch-loop-motions",
        access=PRICED,
    ),
    _op(
        "stitch",
        "Stitch motions with a generated transition",
        "available",
        "Join motion, transition and motion steps with server-side pose sampling and alignment.",
        tools=["stitch"],
        models=["stitch-loop-2.0"],
        docs=f"{DOCS}/capabilities/stitching-sampled-poses",
        access=PRICED,
    ),
    _op(
        "trim_and_save",
        "Trim a motion or save an edited GLTF",
        "available",
        "Native trim, and registration of a host-edited GLTF as a new motion. Free.",
        tools=["trim_motion", "save_motion"],
        access=WRITE,
    ),
    _op(
        "upload_character",
        "Upload a character, auto-rig, re-rig",
        "available",
        "Add an FBX or GLB character; optionally auto-rig, include fingers, face forward, or convert to r15/ue5.",
        tools=["upload_character"],
        models=["autorig"],
        limits=["FBX or GLB", "Up to 30 MiB", "Auto-rigging a mesh without a rig is priced; uploading a rigged character, including re-rigging its skeleton, is free"],
        docs=f"{DOCS}/capabilities/auto-rig-and-upload-character",
        access=WRITE,
    ),
    _op(
        "character_from_image_or_prompt",
        "Create a character from an image or a text prompt",
        "available",
        "Generate a rigged character from one image, or preview prompt images and finalize one.",
        tools=["create_character_from_image", "preview_character_from_prompt", "create_character_from_prompt"],
        models=["character-gen-1.0"],
        limits=["PNG or JPEG, up to 16 MiB and 16 megapixels", "A prompt preview can be finalized once"],
        docs=f"{DOCS}/capabilities/auto-rig-and-add-character",
        access=PRICED,
    ),
    _op(
        "find_assets",
        "List characters and recent motions",
        "available",
        "Name filters over the account's characters and up to 1000 recent organization motions plus examples.",
        tools=["list_characters", "list_motions", "get_motion"],
        limits=["Not a full or semantic library search", "Character catalog read is capped at 16 MiB"],
        docs=f"{DOCS}/capabilities/asset-management",
        access=READ,
    ),
    _op(
        "library_search",
        "Full motion-library and similarity search",
        "planned",
        "Search the whole Uthana library and find similar motions. Not available in this release.",
    ),
    _op(
        "manage_assets",
        "Rename, delete or favorite characters and motions",
        "planned",
        "Available in the web app and API today; not MCP tools in this release.",
        docs=f"{DOCS}/capabilities/asset-management",
    ),
    _op(
        "inspect",
        "Preview and inspect motions",
        "available",
        "Metadata, APNG/WebM previews and decoded preview frames. Free.",
        tools=["get_motion", "get_preview", "get_preview_frame"],
        access=READ,
    ),
    _op(
        "export_motion",
        "Export a motion on a character",
        "available",
        "Retargeted FBX, GLB or BVH with frame rate, mesh, in-place, Roblox, speed and torso options.",
        tools=["check_download_allowed", "download_motion"],
        limits=["24, 30 or 60 fps", "Speed multiplier above 0 and at most 2"],
        docs=f"{DOCS}/capabilities/downloading-motion",
        access="Counts against monthly download seconds on legacy plans; free on pay-as-you-go. "
        "Hosted connections need the mcp:write scope.",
    ),
    _op(
        "hosted_artifacts",
        "Re-download a hosted export",
        "available",
        "Hosted connections only: fetch a fresh link for an export already made, without exporting or charging again.",
        tools=["get_artifact_download"],
        access=READ,
    ),
    _op(
        "export_other_formats",
        "Robot joint trajectories (Unitree G1) and USD/USDZ export",
        "planned",
        "Not available in this release.",
        docs=f"{DOCS}/capabilities/unitree-g1",
    ),
    _op(
        "download_character",
        "Download a character file",
        "planned",
        "Available through the API today; not an MCP tool in this release.",
        docs=f"{DOCS}/capabilities/downloading-character",
    ),
    _op(
        "share_links",
        "Public share links for motions",
        "planned",
        "Not available in this release. Owners can view motions in the Uthana web app.",
    ),
    _op(
        "batch",
        "Batch generation, retargeting and export",
        "planned",
        "Not available in this release; call the single-item tools per item.",
    ),
    _op(
        "realtime",
        "Real-time character control",
        "planned",
        "Experimental streaming control; not a published API capability and not available in this release.",
    ),
    _op(
        "usage_and_pricing",
        "Balance, rates, allowances and estimates",
        "available",
        "Read pay-as-you-go balance and rates, monthly allowances, and estimate a model cost. Never creates work.",
        tools=["get_usage", "estimate_model_cost"],
        docs=f"{DOCS}/pricing",
        access=READ,
    ),
    _op(
        "recovery",
        "Jobs and request recovery",
        "available",
        "Poll a job and read the local receipt for an interrupted request.",
        tools=["get_job", "get_request_status"],
        access=READ,
    ),
    _op(
        "billing_history_and_actions",
        "Billing history, top-ups and auto-recharge",
        "planned",
        "Use the account page today: https://uthana.com/app/account.",
        docs=f"{DOCS}/pricing",
    ),
    _op(
        "account_admin",
        "Profile, API keys and plan changes",
        "not_offered",
        "Account security and plan administration stay in the Uthana web app.",
        docs=f"{DOCS}/capabilities/account-and-organization",
    ),
    _op(
        "editor_control",
        "Scene, pose and editor control (Blender, Unreal, Maya)",
        "not_offered",
        "Host-editor work, not an Uthana platform function. Export from Uthana, then edit with the host's tools.",
    ),
    _op(
        "raw_api",
        "Arbitrary GraphQL execution",
        "not_offered",
        "This MCP maps documented operations to typed tools; it does not run raw API mutations.",
        docs=f"{DOCS}/graphql",
    ),
]

NOTES = [
    "Discovery is read-only: it never submits generation, export or billing work.",
    "status=available means this package has a tool for it; deployment.tools lists what this server registered.",
    "Platform support, this deployment's tools, and the account's eligibility are separate questions. "
    "A listed price never makes an operation callable here.",
    "Rates come from the configured environment at call time (get_usage, estimate_model_cost); "
    "they are not hardcoded here. Published prices: " + PRICING_URL,
]


def catalog(*, version, domain, transport, tools):
    """Static catalog plus facts about this server; no network calls."""
    registered = sorted(tools)
    operations = []
    for row in OPERATIONS:
        entry = dict(row)
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


def account_eligibility(usage):
    """Summarize which priced models this account can currently use, from a usage_snapshot result."""
    rates = (usage.get("payg") or {}).get("rates")
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
        "payg_balance_usd": (usage.get("payg") or {}).get("balance_usd"),
        "monthly_downloads": usage.get("monthly_downloads"),
        "monthly_characters": usage.get("monthly_characters"),
        "models": models,
        "note": "rate_listed=false means the environment returned no rate for this account; null means unknown. "
        "Neither is a permission check: the backend decides each request. Use check_download_allowed for exports.",
    }
