"""Validation shared by the protocol and ordinary Python callers."""

import json
import math
import re

TAR = "cXi2eAP19XwQ"
STAGING = "staging.uthana.com"
PRODUCTION = "uthana.com"


def api_domain(value: str) -> str:
    if value not in (STAGING, PRODUCTION):
        raise ValueError("UTHANA_DOMAIN must be staging.uthana.com or uthana.com; no automatic fallback")
    return value


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Use an identifier of 1–128 letters, digits, underscores, or hyphens")
    return value


def text(value: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Supply nonempty text of at most {maximum} characters")
    return value


def number(value, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"Expected a finite number from {minimum} to {maximum}")
    return value


def object_value(value):
    """GenericScalar values have appeared as dictionaries and JSON strings."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def normalize_job(job: dict) -> dict:
    job_id = identifier(job.get("id"))
    status = job.get("status")
    if not isinstance(status, str):
        raise ValueError("Job response is missing its status")
    result = object_value(job.get("result"))
    # Unwrap only known job envelopes; never mistake arbitrary nested character IDs for motions.
    for _ in range(4):
        if isinstance(result, dict) and "result" in result:
            result = object_value(result["result"])
        else:
            break
    motion_id = None
    if isinstance(result, dict):
        motion_id = result.get("motion_id") or result.get("id")
    if motion_id is not None:
        motion_id = identifier(motion_id)
    terminal = status in {"FINISHED", "FAILED", "CANCELLED", "CANCELED"}
    state = "complete" if status == "FINISHED" and motion_id else "pending"
    if status in {"FAILED", "CANCELLED", "CANCELED"}:
        state = "failed"
    elif status == "FINISHED":
        state = "complete" if motion_id else "unresolved"
    return {
        "job_id": job_id,
        "provider_status": status,
        "state": state,
        "motion_id": motion_id,
        "terminal": terminal,
        "poll_after_seconds": None if terminal else 15,
        "credits_used": None,
        "next_action": "Inspect the existing job; do not regenerate" if state == "unresolved" else None,
    }


def motion_metadata(motion: dict) -> dict:
    motion_id = identifier(motion.get("id"))
    bundles = [a for a in motion.get("assets", []) if a.get("type") == "bundle" and a.get("uid") == motion_id]
    if len(bundles) != 1:
        raise ValueError("Expected one authoritative native motion bundle")
    bundle = bundles[0]
    metadata = object_value(bundle.get("metadata"))
    if not isinstance(metadata, dict):
        raise ValueError("Native motion bundle metadata is missing")
    fps = number(metadata.get("fps"), 1, 1000)
    count = metadata.get("frame_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("Native bundle frame_count is missing or invalid")
    duration = count / fps
    reported = metadata.get("duration")
    if reported is not None and not math.isclose(number(reported, 0, 1e9), duration, abs_tol=1e-6):
        raise ValueError("Native bundle duration disagrees with frame_count / fps")
    digest = bundle.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        raise ValueError("Native bundle SHA-256 is missing or invalid")
    return {
        "motion_id": motion_id,
        "name": motion.get("name"),
        "bundle_id": identifier(bundle.get("id")),
        "bundle_sha256": digest,
        "fps": fps,
        "frame_count": count,
        "duration_seconds": duration,
        "last_sample_seconds": (count - 1) / fps,
        "duration_basis": "native bundle frame_count / fps; native trim includes its last selected frame",
    }
