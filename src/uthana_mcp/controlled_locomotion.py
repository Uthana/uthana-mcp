"""Discoverable path schemas; the shared client owns contract normalization."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from uthana.controlled_locomotion import MAX_COORDINATE, MAX_POINTS, MAX_SPEED_MPS, MIN_SPEED_MPS

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class PathPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    right: Annotated[
        Number,
        Field(
            ge=-MAX_COORDINATE,
            le=MAX_COORDINATE,
            description="Rightward coordinate from the fixed origin, in plan units.",
        ),
    ]
    forward: Annotated[
        Number,
        Field(
            ge=-MAX_COORDINATE,
            le=MAX_COORDINATE,
            description="Forward coordinate from the fixed origin, in plan units.",
        ),
    ]


class PaceChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path_fraction: Annotated[
        Number, Field(ge=0, lt=1, description="Fraction of path length, starting at zero; never a timestamp.")
    ]
    speed_mps: Annotated[
        Number,
        Field(
            ge=MIN_SPEED_MPS,
            le=MAX_SPEED_MPS,
            description="Requested speed in metres per second, even for character-height waypoints.",
        ),
    ]


class PathPlan(BaseModel):
    """Waypoints use a fixed origin, never relative steps or timestamps."""

    model_config = ConfigDict(extra="forbid", strict=True)
    units: Literal["metres", "character_heights"] = Field(
        default="metres", description="Coordinate units; character heights use the reference skeleton height."
    )
    points: Annotated[
        list[PathPoint],
        Field(
            min_length=2,
            max_length=MAX_POINTS,
            description="Fixed-origin waypoints; start at zero and head forward initially.",
        ),
    ]
    pace_changes: Annotated[
        list[PaceChange],
        Field(min_length=1, max_length=MAX_POINTS, description="Strictly increasing path fractions, starting at zero."),
    ]
    style: Literal["neutral_male_a", "crouching", "zombie", "march", "rushed"] = Field(
        default="neutral_male_a", description="Supported style from server discovery."
    )
    allow_slowing: Literal[True] = Field(
        description="Must be true: permit slowing for turns and stopping; exact timing is unsupported."
    )

    @field_validator("allow_slowing", mode="before")
    @classmethod
    def require_slowing(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("allow_slowing must be true; exact timing is not supported")
        return True
