import json

import httpx
import pytest

from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations


@pytest.mark.parametrize(
    "method,args",
    [
        ("usage", ()),
        ("job", ("job1",)),
        ("motion", ("motion1",)),
        ("characters", ()),
        ("motion_catalog", ()),
        ("prices", ()),
        ("locomotion_styles", ()),
        ("download_allowed", ("motion1", "character1")),
    ],
)
async def test_query_authentication_without_path_is_actionable(method, args):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"data": None, "errors": [{"type": "LoginRequired", "path": None, "message": "PRIVATE"}]},
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError, match="Check the API key for the configured Uthana environment") as caught:
            await getattr(api, method)(*args)
        assert caught.value.category == "authentication"
        assert caught.value.outcome == "not_applicable"
        assert "PRIVATE" not in json.dumps(caught.value.details())
        assert "saved request" not in str(caught.value) and "submission" not in str(caught.value)
        assert len(calls) == 1
    finally:
        await api.close()


@pytest.mark.parametrize(
    "types,category",
    [
        (["RoleRequired", "UserAccessRequired"], "permission"),
        (["RegionRestricted"], "region"),
        (["InsufficientBalance"], "balance"),
        (["LoginRequired", "Exception"], "graphql_error"),
        (["LoginRequired", "RoleRequired"], "graphql_error"),
    ],
)
async def test_read_partial_errors_preserve_safe_category_without_claiming_success(tmp_path, types, category):
    body = {
        "data": {"org": {"payg_enabled": True}},
        "errors": [{"type": kind, "path": ["org", "private"], "message": "PRIVATE"} for kind in types],
    }
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    try:
        ops = Operations(api, tmp_path)
        with pytest.raises(APIError) as caught:
            await ops.usage()
        assert caught.value.category == category and caught.value.outcome == "not_applicable"
        assert "PRIVATE" not in json.dumps(caught.value.details())
        assert "saved request" not in str(caught.value)
        with ops.store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 0
    finally:
        await api.close()


@pytest.mark.parametrize(
    "failure,category",
    [
        (401, "authentication"),
        (403, "permission"),
        (429, "rate_limit"),
        (500, "http_error"),
        ("read_timeout", "connection"),
        ("connect_timeout", "connection"),
        ("invalid_json", "provider_error"),
    ],
)
async def test_read_transport_failures_never_refer_to_a_saved_submission(failure, category):
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "read_timeout":
            raise httpx.ReadTimeout("PRIVATE", request=request)
        if failure == "connect_timeout":
            raise httpx.ConnectTimeout("PRIVATE", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="PRIVATE invalid json")
        return httpx.Response(failure, text="PRIVATE")

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as caught:
            await api.usage()
        assert caught.value.category == category and caught.value.outcome == "not_applicable"
        assert "PRIVATE" not in json.dumps(caught.value.details())
        assert "saved request" not in str(caught.value) and "submission" not in str(caught.value)
        assert len(calls) == 1
    finally:
        await api.close()


@pytest.mark.parametrize("case", ["null_path", "missing_path", "nested_path", "partial_data", "unmapped_document"])
async def test_ambiguous_mutation_authentication_keeps_category_but_never_allows_retry(tmp_path, case):
    calls = []
    error = {"type": "LoginRequired", "path": ["create_text_to_motion_job"], "message": "PRIVATE"}
    body = {"data": None, "errors": [error]}
    if case == "null_path":
        error["path"] = None
    elif case == "missing_path":
        error.pop("path")
    elif case == "nested_path":
        error["path"].append("job")
    elif case == "partial_data":
        body["data"] = {"create_text_to_motion_job": {"job": {"id": "accepted1"}}}
    elif case == "unmapped_document":
        error["path"] = ["another_operation"]

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=body)

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        ops = Operations(api, tmp_path)

        async def invoke():
            if case == "unmapped_document":
                # An SDK operation without an explicit mutation context cannot
                # classify a rejection as safe to resubmit.
                return await api._call(api.client.ttm.create_job, "Walk", model="text-to-motion-3.0")
            return await api.generate("Walk", 4, "tar")

        with pytest.raises(RuntimeError, match="may have been accepted"):
            await ops.store.mutation("r", "generate", {}, invoke)
        record = ops.recover_request("r")
        assert record["state"] == "unknown" and record["error"]["category"] == "authentication"
        assert not record["error"]["safe_to_resubmit"]
        assert "PRIVATE" not in json.dumps(record) and "rejected" not in record["error"]["message"]
        with pytest.raises(ValueError, match="unresolved"):
            await ops.store.mutation("r", "generate", {}, invoke)
        assert len(calls) == 1
    finally:
        await api.close()


async def test_known_mutation_cannot_opt_into_read_error_handling():
    def forbidden(request):
        raise AssertionError("No request should be made")

    api = UthanaAPI("fake", transport=httpx.MockTransport(forbidden))
    try:
        with pytest.raises(ValueError, match="cannot use read-only"):
            await api._call(
                api.client.ttm.create_job,
                "Walk",
                model="text-to-motion-3.0",
                mutation_field="create_text_to_motion_job",
                read_only=True,
            )
    finally:
        await api.close()
