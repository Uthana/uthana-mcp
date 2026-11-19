"""Offline contract, durable recovery and terminal-result handling for path jobs."""

import copy
import json
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI
from mcp.server.fastmcp.exceptions import ToolError

from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server
from uthana_mcp.validation import TAR, normalize_job

PLAN = {
    "points": [{"right": 0, "forward": 0}, {"right": 0, "forward": 3}],
    "pace_changes": [{"path_fraction": 0, "speed_mps": 0.8}],
    "allow_slowing": True,
}
MEASUREMENTS = {
    "duration_seconds": 8.0,
    "path_length_m": 3.0,
    "actual_distance_m": 2.95,
    "max_path_error_m": 0.05,
    "endpoint_error_m": 0.05,
    "final_second_drift_m": 0.01,
    "has_stopped": True,
}


async def test_tools_discover_schema_and_backend_enablement_without_mutation(tmp_path: Path) -> None:
    api = FakeAPI()
    server = create_server(Operations(api, tmp_path))
    tools = {tool.name: tool for tool in await server.list_tools()}
    discover = tools["get_controlled_locomotion_options"]
    submit = tools["generate_controlled_locomotion"]
    assert discover.annotations.readOnlyHint is True
    assert submit.annotations.readOnlyHint is False
    schema = submit.inputSchema
    assert set(schema["required"]) == {"request_id", "character_id", "plan"}
    plan = schema["$defs"]["PathPlan"]
    assert plan["additionalProperties"] is False
    assert plan["properties"]["allow_slowing"]["const"] is True
    assert plan["properties"]["points"]["maxItems"] == 16
    result = await server._tool_manager.get_tool(discover.name).run({})
    assert result["enabled"] is False
    assert api.calls == [("controlled_options", {})]


async def test_normalized_plan_replays_without_second_submission(tmp_path: Path) -> None:
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    original = copy.deepcopy(PLAN)
    submitted = await ops.controlled_locomotion("path1", character_id=TAR, plan=PLAN)
    explicit = copy.deepcopy(PLAN) | {"units": "metres", "style": "neutral_male_a"}
    explicit["points"][1]["forward"] = 3.0
    restarted = Operations(api, tmp_path)
    replay = await restarted.controlled_locomotion("path1", character_id=TAR, plan=explicit)
    assert replay["job_id"] == submitted["job_id"] and replay["replayed"]
    assert len(api.calls) == 1 and PLAN == original
    assert replay["billing"]["model"] == "locomotion-1.0"
    assert replay["billing"]["actual_cost_usd"] is None
    assert "get_job" in restarted.recover_request("path1")["job_status_note"]
    with pytest.raises(ValueError, match="different arguments"):
        await restarted.controlled_locomotion("path1", character_id=TAR, plan=explicit | {"style": "zombie"})


@pytest.mark.parametrize(
    "change",
    [
        {"allow_slowing": False},
        {"allow_slowing": 1},
        {"allow_slowing": None},
        {"units": None},
        {"extra": True},
        {"points": [{"right": 1, "forward": 0}, {"right": 0, "forward": 3}]},
        {"pace_changes": [{"path_fraction": 0, "speed_mps": True}]},
        {"pace_changes": [{"path_fraction": 0.3, "speed_mps": 0.8}]},
    ],
)
async def test_invalid_plan_never_claims_receipt_or_submits(tmp_path: Path, change: dict) -> None:
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(ValueError):
        await ops.controlled_locomotion("invalid", character_id=TAR, plan=PLAN | change)
    assert api.calls == []
    assert ops.store.get_request("invalid")["state"] == "not_found"


async def test_unsupported_character_never_submits(tmp_path: Path) -> None:
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(ValueError, match="supported"):
        await ops.controlled_locomotion("unsupported", character_id="unknown", plan=PLAN)
    assert api.calls == []


@pytest.mark.parametrize("allow_slowing", [1, False, None])
async def test_tool_schema_rejects_non_boolean_consent(tmp_path: Path, allow_slowing: object) -> None:
    api = FakeAPI()
    server = create_server(Operations(api, tmp_path))
    with pytest.raises(ToolError):
        await server._tool_manager.get_tool("generate_controlled_locomotion").run(
            {"request_id": "invalid", "character_id": TAR, "plan": PLAN | {"allow_slowing": allow_slowing}}
        )
    assert api.calls == []


async def test_sdk_submission_and_poll_reach_shared_client() -> None:
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        if "create_controlled_locomotion_job" in payload["query"]:
            assert payload["variables"]["plan"]["units"] == "metres"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "create_controlled_locomotion_job": {
                            "job": {"id": "pathjob", "status": "READY"},
                        }
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "job": {
                        "id": "pathjob",
                        "status": "FINISHED",
                        "model": "controlled-locomotion-1",
                        "result": {
                            "result": {"status": "succeeded", "motion_id": "saved", "measurements": MEASUREMENTS}
                        },
                    }
                }
            },
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        submitted = await api.controlled_locomotion(character_id=TAR, plan=PLAN)
        assert submitted["job_id"] == "pathjob" and "motion_id" not in submitted
        result = await api.job(submitted["job_id"])
        assert result["state"] == "complete" and result["motion_id"] == "saved"
        assert result["measurements"] == MEASUREMENTS
        assert len(seen) == 2
    finally:
        await api.close()


@pytest.mark.parametrize("outcome", ["rejected", "unknown"])
async def test_failed_submission_preserves_receipt_recovery(tmp_path: Path, outcome: str) -> None:
    class FailingAPI(FakeAPI):
        async def controlled_locomotion(self, **args):
            self.calls.append(("controlled_locomotion", args))
            raise APIError("submission failed", outcome=outcome)

    api = FailingAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(APIError if outcome == "rejected" else RuntimeError):
        await ops.controlled_locomotion("failure", character_id=TAR, plan=PLAN)
    receipt = ops.recover_request("failure")
    assert receipt["state"] == outcome and receipt["result"] is None
    if outcome == "unknown":
        with pytest.raises(ValueError, match="do not resubmit"):
            await ops.controlled_locomotion("failure", character_id=TAR, plan=PLAN)
        assert len(api.calls) == 1


@pytest.mark.parametrize(
    "provider,result,state",
    [
        ("FINISHED", {"status": "constraints_not_met", "motion_id": None}, "failed"),
        ("FINISHED", {"status": "constraints_not_met", "motion_id": "contradiction"}, "unresolved"),
        ("FINISHED", {"status": "succeeded", "motion_id": None}, "unresolved"),
        ("FINISHED", {"status": "other", "motion_id": "unconfirmed"}, "unresolved"),
        ("FAILED", {"status": "succeeded", "motion_id": "unconfirmed"}, "failed"),
        ("READY", None, "pending"),
        ("FINISHED", None, "unresolved"),
    ],
)
def test_only_confirmed_success_exposes_saved_motion(provider: str, result: object, state: str) -> None:
    normalized = normalize_job(
        {
            "id": "pathjob",
            "status": provider,
            "model": "controlled-locomotion-1",
            "result": json.dumps({"result": result}),
        }
    )
    assert normalized["state"] == state and normalized["motion_id"] is None
    assert normalized["terminal"] is (provider != "READY")
    if state == "unresolved":
        assert "do not regenerate" in normalized["next_action"]


def test_constraint_failure_preserves_only_safe_measurements() -> None:
    result = normalize_job(
        {
            "id": "pathjob",
            "status": "FINISHED",
            "model": "controlled-locomotion-1",
            "result": {
                "status": "constraints_not_met",
                "motion_id": None,
                "measurements": MEASUREMENTS | {"has_stopped": False, "private_debug": "secret"},
            },
        }
    )
    assert result["generation_status"] == "constraints_not_met"
    assert result["measurements"] == MEASUREMENTS | {"has_stopped": False}
    assert result["credits_used"] is None


def test_malformed_measurements_are_not_exposed() -> None:
    result = normalize_job(
        {
            "id": "pathjob",
            "status": "FINISHED",
            "model": "controlled-locomotion-1",
            "result": {
                "status": "succeeded",
                "motion_id": "saved",
                "measurements": MEASUREMENTS | {"duration_seconds": float("nan")},
            },
        }
    )
    assert result["motion_id"] == "saved" and "measurements" not in result


async def test_real_sdk_wire_through_tool_handlers_and_replay(tmp_path: Path) -> None:
    seen = []
    options = {
        "enabled": True,
        "supported_character_ids": [TAR],
        "styles": ["neutral_male_a"],
        "units": ["metres", "character_heights"],
        "limits": {"max_duration_seconds": 20},
        "guidance": ["Allow slowing for turns and stopping."],
    }

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        query = payload["query"]
        if "controlled_locomotion_options" in query:
            return httpx.Response(200, json={"data": {"controlled_locomotion_options": options}})
        if "create_controlled_locomotion_job" in query:
            variables = payload["variables"]
            assert variables["character_id"] == TAR
            assert variables["plan"]["points"] == PLAN["points"]
            assert variables["plan"]["allow_slowing"] is True
            return httpx.Response(
                200,
                json={
                    "data": {
                        "create_controlled_locomotion_job": {
                            "job": {"id": "tooljob", "status": "READY"},
                        }
                    }
                },
            )
        assert payload["variables"] == {"job_id": "tooljob"}
        assert "model" in query
        return httpx.Response(
            200,
            json={
                "data": {
                    "job": {
                        "id": "tooljob",
                        "status": "FINISHED",
                        "model": "controlled-locomotion-1",
                        "result": json.dumps(
                            {
                                "result": {
                                    "status": "constraints_not_met",
                                    "motion_id": None,
                                    "character_id": TAR,
                                    "measurements": MEASUREMENTS | {"has_stopped": False},
                                }
                            }
                        ),
                    }
                }
            },
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        server = create_server(Operations(api, tmp_path))
        tools = server._tool_manager
        discover = await tools.get_tool("get_controlled_locomotion_options").run({})
        assert discover["enabled"] is True
        args = {"request_id": "wire", "character_id": TAR, "plan": PLAN}
        receipt = await tools.get_tool("generate_controlled_locomotion").run(args)
        replay = await tools.get_tool("generate_controlled_locomotion").run(args)
        assert replay["replayed"] and receipt["job_id"] == "tooljob"
        polled = await tools.get_tool("get_job").run({"job_id": receipt["job_id"]})
        assert polled["state"] == "failed" and polled["motion_id"] is None
        assert polled["generation_status"] == "constraints_not_met"
        assert len(seen) == 3  # discovery, one submission, one poll
    finally:
        await api.close()


async def test_older_backend_discovery_reports_error_without_submission(tmp_path: Path) -> None:
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "errors": [{"message": 'Cannot query field "controlled_locomotion_options" on type "Query".'}],
            },
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        server = create_server(Operations(api, tmp_path))
        with pytest.raises(ToolError, match="unavailable"):
            await server._tool_manager.get_tool("get_controlled_locomotion_options").run({})
        assert len(seen) == 1 and "mutation" not in seen[0]["query"]
    finally:
        await api.close()


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "controlled_locomotion.json").read_text())
CASES = [
    dict(
        case,
        input={k: v for k, v in (FIXTURE["base_plan"] | case["overrides"]).items() if k not in case.get("omit", [])},
    )
    for case in FIXTURE["cases"]
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
async def test_shared_plan_fixtures_through_tool_schema(tmp_path: Path, case: dict) -> None:
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    server = create_server(ops)
    args = {"request_id": "fixture", "character_id": TAR, "plan": copy.deepcopy(case["input"])}
    submit = server._tool_manager.get_tool("generate_controlled_locomotion")
    if case["valid"]:
        result = await submit.run(args)
        assert result["job_id"] == "job1"
        assert api.calls[0][1]["plan"] == case["normalized"]
    else:
        with pytest.raises(ToolError):
            await submit.run(args)
        assert api.calls == []
        assert ops.store.get_request("fixture")["state"] == "not_found"
    assert args["plan"] == case["input"]


def test_unrelated_jobs_keep_their_existing_result_contract() -> None:
    result = normalize_job(
        {
            "id": "otherjob",
            "status": "FINISHED",
            "model": "other-model",
            "result": {"status": "succeeded", "id": "legacy_motion"},
        }
    )
    assert result["state"] == "complete" and result["motion_id"] == "legacy_motion"
    assert "generation_status" not in result


def test_exception_envelope_cannot_report_success() -> None:
    result = normalize_job(
        {
            "id": "pathjob",
            "status": "FINISHED",
            "model": "controlled-locomotion-1",
            "result": {"exc": "generation failed", "result": {"status": "succeeded", "motion_id": "saved"}},
        }
    )
    assert result["state"] == "unresolved"
    assert result["motion_id"] is None
