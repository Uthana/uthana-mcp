"""Flat stitch tool discovery; the shared SDK owns request normalization."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from uthana.stitch import validate_stitch_input

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class MotionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    motion_id: Annotated[str, Field(description="Existing source motion ID.")]
    trim_start_frame: Annotated[int, Field(strict=True)] | None = Field(
        default=None, description="First zero-based native frame, inclusive."
    )
    trim_end_frame: Annotated[int, Field(strict=True)] | None = Field(
        default=None, description="Last native frame, inclusive; omit for model context."
    )
    trim_start_seconds: Number | None = Field(
        default=None, description="Source start in seconds; never mix trim units."
    )
    trim_end_seconds: Number | None = Field(
        default=None, description="Source end in seconds; snaps inward to native frames."
    )
    transition_duration_seconds: Number | None = Field(
        default=None, description="Outgoing duration, 0.1-3 seconds; defaults to one. Ignored on the final motion."
    )
    transition_forward_meters: Number | None = Field(
        default=None, description="Outgoing forward gap in meters, relative to ending facing."
    )
    transition_right_meters: Number | None = Field(
        default=None, description="Outgoing rightward gap in meters, relative to ending facing."
    )
    transition_facing_degrees: Number | None = Field(
        default=None, description="Outgoing relative facing in degrees; positive turns right."
    )


class StitchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    character_id: str
    steps: Annotated[list[MotionStep], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def normalize(self) -> Self:
        normalized = validate_stitch_input(self.model_dump(exclude_unset=True))
        return self.model_copy(update={"steps": [MotionStep.model_validate(step) for step in normalized["steps"]]})
