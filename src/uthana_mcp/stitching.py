"""Typed steps shared by server-prepared stitching interfaces."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_OFFSET_METERS = 100
MAX_FRAME_INDEX = 2**53 - 1
MAX_TURN_DEGREES = 180
MIN_TRANSITION_SECONDS = 0.1
MAX_TRANSITION_SECONDS = 3
DEFAULT_TRANSITION_SECONDS = 1.0
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Seconds = Annotated[Number, Field(ge=0)]


class MotionRange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    start_frame: Annotated[int, Field(ge=0, le=MAX_FRAME_INDEX)] | None = Field(
        default=None, description="Zero-based first native frame, inclusive; do not mix with seconds."
    )
    end_frame: Annotated[int, Field(ge=0, le=MAX_FRAME_INDEX)] | None = Field(
        default=None, description="Last native frame, inclusive; omit for safe model context."
    )
    start_seconds: Seconds | None = Field(
        default=None, description="Source start in seconds; snaps inward to native frames."
    )
    end_seconds: Seconds | None = Field(
        default=None, description="Source end in seconds, inclusive; omit for safe model context."
    )

    @model_validator(mode="after")
    def units_and_order(self) -> Self:
        has_frame_range = self.start_frame is not None or self.end_frame is not None
        has_second_range = self.start_seconds is not None or self.end_seconds is not None
        if has_frame_range and has_second_range:
            raise ValueError("Use frames or seconds within a range, not both")
        start = self.start_frame if has_frame_range else self.start_seconds
        end = self.end_frame if has_frame_range else self.end_seconds
        if end is not None and end <= (start or 0):
            raise ValueError("Range end must exceed start")
        if any(value is None for value in self.model_dump(exclude_unset=True).values()):
            raise ValueError("Omit unspecified range fields instead of passing null")
        return self

    def seconds(self, fps: float) -> tuple[float, float | None]:
        if self.start_frame is not None or self.end_frame is not None:
            return (self.start_frame or 0) / fps, self.end_frame / fps if self.end_frame is not None else None
        return self.start_seconds or 0.0, self.end_seconds


class RelativePlacement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    forward_m: Annotated[Number, Field(ge=-MAX_OFFSET_METERS, le=MAX_OFFSET_METERS)] = Field(
        default=0.0, description="Forward gap in meters relative to the preceding motion’s ending facing."
    )
    right_m: Annotated[Number, Field(ge=-MAX_OFFSET_METERS, le=MAX_OFFSET_METERS)] = Field(
        default=0.0, description="Rightward gap in meters relative to the preceding motion’s ending facing."
    )
    turn_degrees: Annotated[Number, Field(ge=-MAX_TURN_DEGREES, le=MAX_TURN_DEGREES)] = Field(
        default=0.0, description="Relative turn in degrees; positive turns right."
    )
    absolute: Literal[False] = Field(
        default=False, description="Only false is supported; absolute spatial placement is reserved."
    )

    @model_validator(mode="before")
    @classmethod
    def reject_absolute(cls, value: object) -> object:
        if isinstance(value, dict) and "absolute" in value and value["absolute"] is not False:
            raise ValueError("Only relative placement (absolute: false) is supported")
        return value


class MotionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["motion"] = Field(description="Motion source step.")
    motion_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$", description="Existing source motion ID.")]
    range: MotionRange = Field(
        default_factory=MotionRange, description="Optional source interval in native frames or seconds, never both."
    )
    placement: RelativePlacement | None = Field(
        default=None,
        description="Arriving-motion placement; omit for automatic continuation, supply an object for explicit offsets.",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_null_placement(cls, value: object) -> object:
        if isinstance(value, dict) and "placement" in value and value["placement"] is None:
            raise ValueError("Omit placement for automatic continuation")
        return value


class TransitionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["transition"] = Field(description="Generated transition between adjacent motions.")
    duration_seconds: Annotated[Number, Field(ge=MIN_TRANSITION_SECONDS, le=MAX_TRANSITION_SECONDS)] = Field(
        default=DEFAULT_TRANSITION_SECONDS, description="Transition seconds, 0.1-3; quantized to model frames."
    )


Step = Annotated[MotionStep | TransitionStep, Field(discriminator="type")]


class StitchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    character_id: Annotated[
        str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$", description="Character used for all motion steps.")
    ]
    steps: Annotated[
        list[Step],
        Field(min_length=3, max_length=3, description="Exactly motion, transition, motion in playback order."),
    ]

    @model_validator(mode="after")
    def sequence(self) -> Self:
        first, transition, last = self.steps
        if (
            not isinstance(first, MotionStep)
            or not isinstance(transition, TransitionStep)
            or not isinstance(last, MotionStep)
        ):
            raise ValueError("Supported sequence is motion, transition, motion")
        if first.placement is not None:
            raise ValueError("Placement is supported only on the arriving motion")
        return self
