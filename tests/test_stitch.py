"""Stitch source verification and mutation recovery remain enforced with typed steps."""

import asyncio

import pytest
from fakes import FakeAPI

from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.validation import TAR


def options():
    return {
        "character_id": TAR,
        "steps": [
            {"type": "motion", "motion_id": "motion1"},
            {"type": "transition"},
            {"type": "motion", "motion_id": "motion2"},
        ],
    }


@pytest.mark.parametrize(
    "failure", ["returned_prefix", "returned_suffix", "suffix_changed", "reused_bundle", "metadata"]
)
async def test_stitch_preservation_failure_keeps_completed_id(tmp_path, failure):
    api = FakeAPI()
    original = api.stitch

    async def stitch(*args):
        result = await original(*args)
        if failure == "returned_prefix":
            result["motion_id"] = "motion1"
        elif failure == "returned_suffix":
            result["motion_id"] = "motion2"
        elif failure == "suffix_changed":
            api.motions["motion2"]["bundle_sha256"] = "b" * 64
        elif failure == "reused_bundle":
            api.motions["stitched1"]["bundle_id"] = "bundle_motion2"
        else:
            api.fail_verification = True
        return result

    api.stitch = stitch
    ops = Operations(api, tmp_path)
    result = await ops.stitch("join1", options())
    assert result["verification_status"] == ("unverified" if failure == "metadata" else "failed")
    recovered = ops.recover_request("join1")
    assert recovered["state"] == "complete" and recovered["result"]["motion_id"] == result["motion_id"]
    assert (await ops.stitch("join1", options()))["replayed"]
    assert len(api.calls) == 1


@pytest.mark.parametrize("outcome", ["rejected", "unknown", "cancelled"])
async def test_stitch_retries_only_confirmed_rejection(tmp_path, outcome):
    api = FakeAPI()
    original = api.stitch
    writes = []

    async def failure(*args):
        writes.append(args)
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        raise APIError("Synthetic failure", outcome=outcome)

    api.stitch = failure
    ops = Operations(api, tmp_path)
    with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else RuntimeError):
        await ops.stitch("join1", options())
    status = ops.recover_request("join1")
    assert status["state"] == ("rejected" if outcome == "rejected" else "unknown")
    api.stitch = original
    resumed = Operations(api, tmp_path)
    if outcome == "rejected":
        assert (await resumed.stitch("join1", options()))["motion_id"] == "stitched1"
    else:
        with pytest.raises(ValueError, match="pending or unresolved"):
            await resumed.stitch("join1", options())
        assert not api.calls
    assert len(writes) == 1


async def test_pending_stitch_cannot_be_submitted_concurrently(tmp_path):
    api = FakeAPI()
    entered, release = asyncio.Event(), asyncio.Event()
    original = api.stitch

    async def delayed(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    api.stitch = delayed
    first = asyncio.create_task(Operations(api, tmp_path).stitch("join1", options()))
    await entered.wait()
    try:
        with pytest.raises(ValueError, match="pending or unresolved"):
            await Operations(api, tmp_path).stitch("join1", options())
    finally:
        release.set()
        await first
    assert len(api.calls) == 1
