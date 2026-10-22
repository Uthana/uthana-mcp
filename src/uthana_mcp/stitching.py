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
    x: Annotated[Scalar, Field(description="World X position in meters, -1000000 to 1000000; Y is vertical.")]
    y: Annotated[Scalar, Field(description="World Y position in meters, -1000000 to 1000000; Y is vertical.")]
    z: Annotated[Scalar, Field(description="World Z position in meters, -1000000 to 1000000; Y is vertical.")]


class Quaternion(BaseModel):
    """Sampled world rotation in x/y/z/w order, approximately unit length."""

    model_config = ConfigDict(extra="forbid")
    x: Annotated[Unit, Field(description="Quaternion x component, -1 to 1; total length must be within 0.001 of 1.")]
    y: Annotated[Unit, Field(description="Quaternion y component, -1 to 1; total length must be within 0.001 of 1.")]
    z: Annotated[Unit, Field(description="Quaternion z component, -1 to 1; total length must be within 0.001 of 1.")]
    w: Annotated[Unit, Field(description="Quaternion w component, -1 to 1; total length must be within 0.001 of 1.")]

    @model_validator(mode="after")
    def unit_length(self):
        if not math.isclose(math.hypot(self.x, self.y, self.z, self.w), 1, abs_tol=1e-3):
            raise ValueError("Supply a sampled unit quaternion")
        return self


class PelvisState(BaseModel):
    """Pelvis world transform and hip-derived facing yaw in radians."""

    model_config = ConfigDict(extra="forbid")
    pelvis_world_pos: Annotated[
        Vector3, Field(description="Pelvis world position in meters, Y up; include all ancestor scale transforms.")
    ]
    pelvis_world_rot: Annotated[Quaternion, Field(description="Pelvis world rotation as a unit x/y/z/w quaternion.")]
    hips_forward_facing_world_yaw: Annotated[
        Scalar,
        Field(
            description="Hip-derived facing yaw in radians, -1000000 to 1000000. Calibrate the unresolved hip-axis convention described in STITCHING.md."
        ),
    ]


class StitchClip(BaseModel):
    """Clip sampled by a motion loader on the specified character in a shared scene.

    Get bundle identity from get_motion before sampling; it is checked before
    submission. Pose values must come from the real animation, not guessed zeros.
    """

    model_config = ConfigDict(extra="forbid")
    motion_id: Annotated[Id, Field(description="Existing motion ID for this clip.")]
    sampled_character_id: Annotated[
        Id, Field(description="Character used to evaluate these poses; must match character_id.")
    ]
    source_bundle_id: Annotated[Id, Field(description="Native source-file ID returned by get_motion before sampling.")]
    source_bundle_sha256: Annotated[
        Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")],
        Field(description="64 hexadecimal digits identifying the source file returned by get_motion."),
    ]
    start_seconds: Annotated[
        Seconds, Field(description="Native sample time in seconds, 0-1000000, less than end_seconds.")
    ]
    end_seconds: Annotated[
        Seconds,
        Field(
            description="Native sample time in seconds, greater than start_seconds and no later than last_sample_seconds."
        ),
    ]
    root_node_world_pos: Annotated[
        Vector3, Field(description="Root world position in meters, Y up; include all ancestor scale transforms.")
    ]
    root_node_world_rot: Annotated[Quaternion, Field(description="Root world rotation as a unit x/y/z/w quaternion.")]
    at_zero_time: Annotated[PelvisState, Field(description="Pelvis state evaluated at time zero.")]
    at_lower_trim_time: Annotated[PelvisState, Field(description="Pelvis state evaluated at start_seconds.")]
    at_upper_trim_time: Annotated[PelvisState, Field(description="Pelvis state evaluated at end_seconds.")]

    @model_validator(mode="after")
    def ordered_times(self):
        if self.start_seconds >= self.end_seconds:
            raise ValueError(
                f"start_seconds must be less than end_seconds (received {self.start_seconds}, {self.end_seconds})"
            )
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


class StitchPlacement(BaseModel):
    """Meters relative to prefix ending facing; positive degrees turn right."""

    model_config = ConfigDict(extra="forbid", strict=True)
    forward_m: Annotated[
        Annotated[float, Field(strict=True, ge=-100, le=100, allow_inf_nan=False)] | None,
        Field(description="Forward gap in meters; omit to continue travel, set zero for no forward gap."),
    ] = None
    right_m: Annotated[
        float,
        Field(
            strict=True,
            ge=-100,
            le=100,
            allow_inf_nan=False,
            description="Gap in meters relative to prefix ending facing; explicit zero requests zero offset.",
        ),
    ] = 0.0
    facing_degrees: Annotated[
        float,
        Field(
            strict=True,
            ge=-180,
            le=180,
            allow_inf_nan=False,
            description="Relative facing in degrees; positive turns right, default zero.",
        ),
    ] = 0.0


class AutoStitchOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    character_id: Id
    prefix_motion_id: Id
    suffix_motion_id: Id
    stitch_duration: Annotated[float, Field(strict=True, ge=0.1, le=3, allow_inf_nan=False)] = 1.0
    prefix_start_seconds: Seconds = 0.0
    prefix_end_seconds: Seconds | None = None
    suffix_start_seconds: Seconds = 0.0
    suffix_end_seconds: Seconds | None = None
    placement: StitchPlacement = Field(default_factory=StitchPlacement)

    @model_validator(mode="after")
    def ordered_trims(self):
        for label in ("prefix", "suffix"):
            start = getattr(self, f"{label}_start_seconds")
            end = getattr(self, f"{label}_end_seconds")
            if end is not None and end <= start:
                raise ValueError(f"{label}_end_seconds must exceed {label}_start_seconds")
        return self
