"""Numeric replay identity and compatibility with receipts from before normalization."""

import asyncio
import hashlib
import json

import pytest

from uthana_mcp.fingerprints import fingerprint, matches
from uthana_mcp.store import Store


def legacy_hash(operation, args):
    return hashlib.sha256(json.dumps([operation, args], sort_keys=True, allow_nan=False).encode()).hexdigest()


@pytest.mark.parametrize(
    "operation,old,new",
    [
        ("generate", {"duration_seconds": 4}, {"duration_seconds": 4.0}),
        ("generate_v2", {"duration_seconds": 4.0}, {"duration_seconds": 4}),
        (
            "locomotion",
            {"strides": 4, "move_speed": 1.0, "travel_angle": -0.0},
            {"strides": 4.0, "move_speed": 1, "travel_angle": 0},
        ),
        ("trim", {"start_seconds": 0.0, "end_seconds": 3}, {"start_seconds": 0, "end_seconds": 3.0}),
        ("download", {"fps": 30, "speed_multiplier": 2.0}, {"fps": 30.0, "speed_multiplier": 2}),
    ],
)
async def test_legacy_numeric_replay_preserves_original_receipt(tmp_path, operation, old, new):
    store = Store(tmp_path, "legacy")
    digest = legacy_hash(operation, old)
    result = {"motion_id": "original", "historical_field": "unchanged"}
    with store.connect() as db:
        db.execute(
            "INSERT INTO requests(id,operation,fingerprint,state,result,updated) VALUES(?,?,?,?,?,?)",
            ("r", operation, digest, "complete", json.dumps(result), 1),
        )

    async def never_invoke():
        raise AssertionError("Completed receipts must not call Uthana again")

    restarted = Store(tmp_path, "legacy")
    assert restarted.replay("r", operation, new) == {**result, "replayed": True}
    assert await restarted.mutation("r", operation, new, never_invoke) == {**result, "replayed": True}
    with store.connect() as db:
        assert db.execute("SELECT fingerprint,updated FROM requests").fetchone() == (digest, 1)


@pytest.mark.parametrize("state", ["pending", "unknown"])
async def test_equivalent_legacy_unresolved_requests_still_block(tmp_path, state):
    store = Store(tmp_path, "legacy")
    with store.connect() as db:
        db.execute(
            "INSERT INTO requests(id,operation,fingerprint,state,updated) VALUES(?,?,?,?,?)",
            ("r", "generate", legacy_hash("generate", {"duration_seconds": 4}), state, 1),
        )

    async def never_invoke():
        raise AssertionError("Unresolved operations must not be resubmitted")

    with pytest.raises(ValueError, match="unresolved"):
        await store.mutation("r", "generate", {"duration_seconds": 4.0}, never_invoke)
    assert store.get_request("r")["state"] == state


async def test_equivalent_legacy_rejected_claim_is_atomic(tmp_path):
    store = Store(tmp_path, "legacy")
    with store.connect() as db:
        db.execute(
            "INSERT INTO requests(id,operation,fingerprint,state,updated) VALUES(?,?,?,?,?)",
            ("r", "generate", legacy_hash("generate", {"duration_seconds": 4}), "rejected", 1),
        )
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def invoke():
        calls.append(True)
        started.set()
        await release.wait()
        return {"job_id": "once"}

    task = asyncio.create_task(store.mutation("r", "generate", {"duration_seconds": 4.0}, invoke))
    await started.wait()
    try:
        with pytest.raises(ValueError, match="unresolved"):
            await Store(tmp_path, "legacy").mutation("r", "generate", {"duration_seconds": 4}, invoke)
    finally:
        release.set()
    await task
    assert calls == [True]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("changed", [5, 4.01, True, "4", None])
def test_different_values_and_types_remain_different(legacy, changed):
    args = {"duration_seconds": 4, "prompt": "Walk"}
    saved = legacy_hash("generate", args) if legacy else fingerprint("generate", args)
    assert not matches(saved, "generate", {**args, "duration_seconds": changed})
    assert not matches(saved, "generate_v2", args)
    assert not matches(saved, "generate", {**args, "prompt": "Run"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_rejected(value):
    with pytest.raises(ValueError):
        fingerprint("generate", {"duration_seconds": value})


def test_large_integers_do_not_collapse_to_rounded_floats():
    exact = {"duration_seconds": 2**53 + 1}
    rounded = {"duration_seconds": float(2**53 + 1)}
    assert fingerprint("generate", exact) != fingerprint("generate", rounded)
    assert not matches(legacy_hash("generate", exact), "generate", rounded)
    assert not matches(legacy_hash("generate", rounded), "generate", exact)
    enormous = {"duration_seconds": 10**400}
    assert matches(legacy_hash("generate", enormous), "generate", enormous)
    assert not matches(legacy_hash("generate", rounded), "generate", enormous)


def test_nested_normalization_preserves_boolean_identity():
    assert fingerprint("x", {"a": [4, -0.0, {"b": 2.0}]}) == fingerprint("x", {"a": [4.0, 0, {"b": 2}]})
    assert fingerprint("x", {"a": True}) != fingerprint("x", {"a": 1})
