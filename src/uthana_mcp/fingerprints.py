"""Stable numeric request identity with bounded compatibility for legacy receipts."""

import hashlib
import itertools
import json
import math

# These are the numeric fields in the existing operation receipts. Limiting legacy
# alternatives to the known contract avoids an exponential walk of arbitrary input.
_LEGACY_NUMERIC_FIELDS = {
    "generate": ("duration_seconds",),
    "generate_v2": ("duration_seconds",),
    "locomotion": ("strides", "move_speed", "travel_angle"),
    "trim": ("start_seconds", "end_seconds"),
    "download": ("fps", "speed_multiplier"),
}


def _digest(operation, args):
    return hashlib.sha256(json.dumps([operation, args], sort_keys=True, allow_nan=False).encode()).hexdigest()


def _normalize(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def fingerprint(operation, args):
    # Prefix separates canonical hashes from receipts created with raw JSON hashing.
    # Booleans and strings retain their types; non-finite values still fail encoding.
    return "n1:" + _digest(operation, _normalize(args))


def _legacy_numbers(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return (value,)
    try:
        numeric = float(value)
    except OverflowError:
        return (value,)
    if not math.isfinite(numeric) or not numeric.is_integer() or numeric != value:
        return (value,)
    if numeric == 0:
        return (0, 0.0, -0.0)
    return (int(numeric), numeric)


def matches(saved, operation, args):
    if saved.startswith("n1:"):
        return saved == fingerprint(operation, args)
    # Exact legacy matches work for every historical operation, even beyond the
    # known numeric fields. Old receipts never stored their original arguments.
    if saved == _digest(operation, args):
        return True
    fields = [key for key in _LEGACY_NUMERIC_FIELDS.get(operation, ()) if key in args]
    for values in itertools.product(*(_legacy_numbers(args[key]) for key in fields)):
        candidate = {**args, **dict(zip(fields, values))}
        if saved == _digest(operation, candidate):
            return True
    return False
