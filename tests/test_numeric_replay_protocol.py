"""Equivalent JSON numbers must recover the same operation through real MCP."""

import sys
from itertools import permutations
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import uthana_mcp


@pytest.mark.parametrize(
    ("tool", "numeric_argument", "default", "identity_field"),
    [
        ("generate_motion", "duration_seconds", 4, "job_id"),
        ("generate_motion_v2", "duration_seconds", 4, "motion_id"),
        ("generate_locomotion", "travel_angle", 0, "motion_id"),
    ],
)
@pytest.mark.parametrize(
    ("first_form", "second_form"),
    list(permutations(("omitted", "integer", "float"), 2)),
)
async def test_equivalent_numeric_arguments_replay_over_stdio(
    tmp_path, tool, numeric_argument, default, identity_field, first_form, second_form
):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("stdio_fixture.py")), str(tmp_path)],
        # The SDK intentionally does not inherit PYTHONPATH. Match the package
        # imported by this test, whether the suite targets source or a wheel.
        env={"PYTHONPATH": str(Path(uthana_mcp.__file__).resolve().parent.parent)},
    )
    common = {"request_id": "same-intent"}
    if tool != "generate_locomotion":
        common["prompt"] = "Walk"

    def arguments(form):
        if form == "omitted":
            return dict(common)
        return {**common, numeric_argument: float(default) if form == "float" else default}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            original = await client.call_tool(tool, arguments(first_form))
            assert not original.isError, original.content
            original_data = original.structuredContent
            assert original_data["replayed"] is False
            repeated = await client.call_tool(tool, arguments(second_form))
            assert not repeated.isError, repeated.content
            repeated_data = repeated.structuredContent
            assert repeated_data["replayed"] is True
            assert repeated_data["request_id"] == original_data["request_id"] == "same-intent"
            assert repeated_data[identity_field] == original_data[identity_field]
            assert {key: value for key, value in repeated_data.items() if key != "replayed"} == {
                key: value for key, value in original_data.items() if key != "replayed"
            }
            recovered = await client.call_tool("get_request_status", {"request_id": "same-intent"})
            assert not recovered.isError, recovered.content
            assert recovered.structuredContent["state"] == "complete"
            assert recovered.structuredContent["result"][identity_field] == original_data[identity_field]
