"""Validation shared by the protocol and ordinary Python callers."""

import json
import math
import re
from typing import Literal, NotRequired, TypedDict, get_args

TAR = "cXi2eAP19XwQ"
UTHANA_DOMAIN = "uthana.com"
Ttm3Model = Literal["text-to-motion-3.0", "text-to-motion-3.0-lite", "text-to-motion-3.0-mini"]
TTM3_MODELS = get_args(Ttm3Model)
MIN_TTM3_DURATION_SECONDS = 4
MIN_LITE_MINI_DURATION_SECONDS = 5


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


class ControlledJobResult(TypedDict):
    job_id: str
    provider_status: str
    state: str
    motion_id: str | None
    terminal: bool
    poll_after_seconds: int | None
    credits_used: None
    next_action: str | None
    generation_status: str | None
    measurements: NotRequired[dict[str, float | bool]]


def _normalize_controlled_job(*, job_id: str, provider_status: str, result: object) -> ControlledJobResult:
    """Expose only confirmed saved IDs; constraint failure is terminal, not an unknown success."""
    is_terminal = provider_status in {"FINISHED", "FAILED", "CANCELLED", "CANCELED"}
    normalized: ControlledJobResult = {
        "job_id": job_id,
        "provider_status": provider_status,
        "state": "unresolved" if provider_status == "FINISHED" else "failed" if is_terminal else "pending",
        "motion_id": None,
        "terminal": is_terminal,
        "poll_after_seconds": None if is_terminal else 15,
        "credits_used": None,
        "next_action": None,
        "generation_status": None,
    }
    if provider_status == "FINISHED" and isinstance(result, dict):
        outcome = result.get("status")
        if outcome == "constraints_not_met" and "motion_id" in result and result["motion_id"] is None:
            normalized.update(
                state="failed",
                generation_status=outcome,
                next_action="No animation was saved because the path constraints were not met. "
                "Review the plan; submit a revised request only within the user's authorized scope and budget.",
            )
        elif outcome == "succeeded":
            try:
                motion_id = identifier(result.get("motion_id"))
            except ValueError:
                pass
            else:
                normalized.update(state="complete", motion_id=motion_id, generation_status=outcome)
        measurements = result.get("measurements")
        if isinstance(measurements, dict):
            fields = (
                "duration_seconds",
                "path_length_m",
                "actual_distance_m",
                "max_path_error_m",
                "endpoint_error_m",
                "final_second_drift_m",
            )
            has_measurements = all(
                type(measurements.get(key)) in {int, float}
                and (type(measurements[key]) is int or math.isfinite(measurements[key]))
                and measurements[key] >= 0
                for key in fields
            )
            if has_measurements and type(measurements.get("has_stopped")) is bool:
                normalized["measurements"] = {key: measurements[key] for key in (*fields, "has_stopped")}
    if normalized["state"] == "unresolved":
        normalized["next_action"] = "Inspect the existing job; do not regenerate"
    return normalized


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
    if job.get("model") == "controlled-locomotion-1":
        return _normalize_controlled_job(job_id=job_id, provider_status=status, result=result)
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


class AssetRecord(TypedDict):
    id: str
    name: str | None
    org_id: str
    deleted: str | None


def asset_record(row: object) -> AssetRecord:
    """Normalize a character or motion record returned by a read or lifecycle mutation."""
    if not isinstance(row, dict):
        raise ValueError("Expected a character or motion record")
    name, deleted = row.get("name"), row.get("deleted")
    if not (name is None or isinstance(name, str)) or not (deleted is None or isinstance(deleted, str)):
        raise ValueError("Character or motion record has an invalid name or deletion time")
    return {"id": identifier(row.get("id")), "name": name, "org_id": identifier(row.get("org_id")), "deleted": deleted}


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
