"""Explicit sampled-pose contract for stitching two existing motions."""

import math
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Scalar = Annotated[float, Field(strict=True, ge=-1e6, le=1e6, allow_inf_nan=False)]
Seconds = Annotated[float, Field(strict=True, ge=0, le=1e6, allow_inf_nan=False)]
Unit = Annotated[float, Field(strict=True, ge=-1, le=1, allow_inf_nan=False)]


class Vector3(BaseModel):
    """World position in meters, Y up; x/z are horizontal."""

    model_config = ConfigDict(extra="forbid")
    x: Scalar
    y: Scalar
    z: Scalar


class Quaternion(BaseModel):
    """Sampled world rotation in x/y/z/w order, approximately unit length."""

    model_config = ConfigDict(extra="forbid")
    x: Unit
    y: Unit
    z: Unit
    w: Unit

    @model_validator(mode="after")
    def unit_length(self):
        if not math.isclose(math.hypot(self.x, self.y, self.z, self.w), 1, abs_tol=1e-3):
            raise ValueError("Supply a sampled unit quaternion")
        return self


class PelvisState(BaseModel):
    """Pelvis world transform and hip-derived facing yaw in radians."""

    model_config = ConfigDict(extra="forbid")
    pelvis_world_pos: Vector3
    pelvis_world_rot: Quaternion
    hips_forward_facing_world_yaw: Scalar


class StitchClip(BaseModel):
    """Clip sampled by a motion loader on the specified character in a shared scene.

    Get bundle identity from get_motion before sampling; it is checked before
    submission. Pose values must come from the real animation, not guessed zeros.
    """

    model_config = ConfigDict(extra="forbid")
    motion_id: Id
    sampled_character_id: Id
    source_bundle_id: Id
    source_bundle_sha256: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")]
    start_seconds: Seconds
    end_seconds: Seconds
    root_node_world_pos: Vector3
    root_node_world_rot: Quaternion
    at_zero_time: PelvisState
    at_lower_trim_time: PelvisState
    at_upper_trim_time: PelvisState

    @model_validator(mode="after")
    def ordered_times(self):
        if self.start_seconds >= self.end_seconds:
            raise ValueError("Require start_seconds < end_seconds")
        return self


def api_clip(clip, source, character_id, stitch_duration, prompt):
    """Use authoritative native timing; keep caller-supplied poses explicit."""
    if clip["sampled_character_id"] != character_id:
        raise ValueError("Both clips must be sampled on the selected character")
    if (
        clip["source_bundle_id"] != source["bundle_id"]
        or clip["source_bundle_sha256"].lower() != source["bundle_sha256"].lower()
    ):
        raise ValueError("Sampled source bundle changed; inspect the current motion and resample before stitching")
    start, end = clip["start_seconds"], clip["end_seconds"]
    if end > source["last_sample_seconds"]:
        raise ValueError("Stitch trim times must be within actual native samples, not beyond the final frame")
    if int(start * source["fps"]) >= int(end * source["fps"]):
        raise ValueError("Stitch selection must span at least one native frame interval")
    duration = source["duration_seconds"]
    return {
        "motion_id": clip["motion_id"],
        "prompt": prompt,
        "stitch_loop": False,
        "stitch_duration": stitch_duration,
        "motion_duration": duration,
        "motion_lower_trim_time": start,
        "motion_upper_trim_time": end,
        "motion_lower_trim_fraction": start / duration,
        "motion_upper_trim_fraction": end / duration,
        **{
            key: clip[key]
            for key in (
                "root_node_world_pos",
                "root_node_world_rot",
                "at_zero_time",
                "at_lower_trim_time",
                "at_upper_trim_time",
            )
        },
    }
