"""Behavior at the MCP/shared-client boundary, using the real SDK with fake HTTP."""

import hashlib
import json

import httpx
import pytest
from uthana import Uthana

from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.store import Store
from uthana_mcp.validation import TAR


def test_sdk_initialization_has_no_network_or_telemetry(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Initialization must not contact Uthana or emit analytics")

    monkeypatch.setattr(httpx.Client, "post", forbidden)
    api = UthanaAPI("fake", transport=httpx.MockTransport(forbidden))
    assert isinstance(api.client, Uthana)
    api.client.close()


async def test_old_completed_receipt_replays_without_sdk_submission(tmp_path):
    scope = hashlib.sha256(b"uthana.com:fake").hexdigest()
    store = Store(tmp_path, scope)
    args = {"prompt": "Walk", "duration_seconds": 4, "character_id": TAR}
    legacy_hash = hashlib.sha256(json.dumps(["generate", args], sort_keys=True).encode()).hexdigest()
    original = {"job_id": "before_sdk", "character_id": TAR, "historical_field": "preserved"}
    with store.connect() as db:
        db.execute(
            "INSERT INTO requests(id,operation,fingerprint,state,result,updated) VALUES(?,?,?,?,?,?)",
            ("existing", "generate", legacy_hash, "complete", json.dumps(original), 1),
        )

    def forbidden(request):
        raise AssertionError("Switching to the shared client must not regenerate existing work")

    api = UthanaAPI("fake", "uthana.com", transport=httpx.MockTransport(forbidden))
    try:
        result = await Operations(api, tmp_path).generate("existing", "Walk", 4.0)
        assert result == {**original, "replayed": True}
    finally:
        await api.close()


@pytest.mark.parametrize("read_only", [True, False])
async def test_sdk_response_limit_preserves_read_and_unknown_mutation_semantics(tmp_path, read_only):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    ops = Operations(api, tmp_path)
    try:
        if read_only:
            with pytest.raises(APIError, match="size limit") as error:
                await api.usage()
            assert error.value.outcome == "not_applicable"
        else:
            with pytest.raises(RuntimeError, match="size limit"):
                await ops.generate("oversized", "Walk")
            assert ops.recover_request("oversized")["state"] == "unknown"
            with pytest.raises(ValueError, match="unresolved"):
                await ops.generate("oversized", "Walk")
        assert len(calls) == 1
    finally:
        await api.close()
