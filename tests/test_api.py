import json

import httpx
import pytest

from uthana_mcp.api import APIError, UthanaAPI
from uthana_mcp.attribution import MCPTransport
from uthana_mcp.validation import motion_metadata, normalize_job


@pytest.mark.parametrize("token", ["delegated-token", " \tdelegated-token\r\n"])
async def test_hosted_token_is_trimmed_by_sdk(token):
    seen = []

    def respond(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"data": {"org": {"payg_prices": []}}})

    api = UthanaAPI(None, access_token=token, scope="verified-identity", transport=httpx.MockTransport(respond))
    try:
        await api.prices()
        await api.client._graphql("{ org { payg_prices { id } } }")
    finally:
        await api.close()
    assert seen == ["Bearer delegated-token", "Bearer delegated-token"]


async def test_robot_download_uses_published_client_csv_route() -> None:
    seen = []
    body = b"Frame,root_x\n0,0.0\n"

    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=body)

    api = UthanaAPI("fake", "uthana.com", transport=httpx.MockTransport(respond))
    try:
        assert await api.download_robot(motion_id="m1", character_id="c1", robot="unitree_g1", fps=24) == body
        assert seen[0].url.path == "/motion/file/motion_viewer/c1/m1/csv/unitree_g1_c1-m1.csv"
        assert dict(seen[0].url.params) == {"fps": "24"}
        assert seen[0].extensions["timeout"]["read"] == 660.0
    finally:
        await api.close()


@pytest.mark.parametrize("domain", ["uthana.com", "other.example.com"])
async def test_uses_configured_host(domain):
    api = UthanaAPI("fake", domain)
    assert api.domain == domain
    await api.close()


@pytest.mark.parametrize("domain", ["uthana.com", "other.example.com:8443"])
async def test_mcp_requests_are_attributed_only_to_configured_api_host(domain):
    seen = []

    class CloseAwareTransport(httpx.AsyncBaseTransport):
        closed = False

        async def handle_async_request(self, request):
            assert not self.closed
            seen.append(request)
            return httpx.Response(200, json={"data": {"org": {"payg_prices": []}}})

        async def aclose(self):
            self.closed = True

    upstream = CloseAwareTransport()
    api = UthanaAPI("fake", domain, transport=upstream)
    try:
        await api.prices()
        await api.prices()
        assert seen[0].headers["X-Uthana-AppId"] == "mcp"
        assert seen[0].headers["User-Agent"].startswith("uthana-mcp/")
        assert seen[0].headers["authorization"] == "Basic ZmFrZTo="
        assert seen[1].headers["X-Uthana-AppId"] == "mcp"
    finally:
        await api.close()
    assert upstream.closed

    external = []

    def respond(request):
        external.append(request)
        return httpx.Response(200, content=b"external")

    transport = MCPTransport("uthana.com", httpx.MockTransport(respond))
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://storage.example/file")
        await client.get("https://uthana.com.evil.example/file")
    assert all("X-Uthana-AppId" not in request.headers for request in external)


@pytest.mark.parametrize(
    "result",
    [
        {"result": {"id": "motion1"}},
        {"id": "motion1"},
        {"motion_id": "motion1"},
        json.dumps({"result": {"id": "motion1"}}),
        {"result": json.dumps({"motion_id": "motion1"})},
    ],
)
def test_completed_job_response_shapes(result):
    normalized = normalize_job({"id": "job1", "status": "FINISHED", "result": result})
    assert normalized["motion_id"] == "motion1" and normalized["state"] == "complete"
    assert normalized["terminal"] and normalized["poll_after_seconds"] is None


def test_finished_without_id_and_failed_are_not_success():
    assert normalize_job({"id": "job1", "status": "FINISHED", "result": "bad-json"})["state"] == "unresolved"
    assert normalize_job({"id": "job1", "status": "FAILED", "result": None})["state"] == "failed"


def test_native_metadata_validation():
    motion = {
        "id": "motion1",
        "name": "Jump",
        "assets": [
            {
                "id": "bundle1",
                "uid": "motion1",
                "type": "bundle",
                "sha256": "a" * 64,
                "metadata": {"fps": 30, "frame_count": 120, "duration": 4},
            }
        ],
    }
    result = motion_metadata(motion)
    assert result["duration_seconds"] == 4
    assert result["last_sample_seconds"] == 119 / 30
    motion["assets"][0]["metadata"]["duration"] = 8
    with pytest.raises(ValueError, match="disagrees"):
        motion_metadata(motion)


@pytest.mark.parametrize("domain", ["uthana.com", "other.example.com"])
async def test_api_graphql_documents_and_export_routes(domain):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == domain
        assert request.headers["authorization"] == "Basic ZmFrZTo="
        if request.url.path == "/graphql":
            document = json.loads(request.content)
            if "create_text_to_motion_job(" in document["query"]:
                assert document["variables"]["length"] == 4
                assert document["variables"]["model"] == "text-to-motion-3.0"
                assert document["variables"]["rewrite_prompt"] is True
                return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})
            if "trim_and_loop_motion(" in document["query"]:
                assert "loop: false" in document["query"]
                assert document["variables"]["start"] == 0.25
                return httpx.Response(200, json={"data": {"trim_and_loop_motion": {"motion": {"id": "trimmed1"}}}})
        if request.url.path.endswith("preview.png"):
            return httpx.Response(200, content=b"apng-fixture")
        assert request.url.path == "/motion/file/motion_viewer/roblox1/motion1/fbx/roblox1-motion1.fbx"
        assert dict(request.url.params) == {
            "fps": "30",
            "no_mesh": "false",
            "in_place": "true",
            "roblox_compatible": "true",
        }
        return httpx.Response(200, content=b"export")

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        assert (await api.generate("Jump", 4, "tar"))["job_id"] == "job1"
        assert (await api.trim("motion1", 0.25, 0.75, "Middle"))["motion_id"] == "trimmed1"
        await api.preview("motion1", "tar", "apng")
        await api.download("motion1", "roblox1", "fbx", 30, True, True, True)
        assert len(requests) == 4
    finally:
        await api.close()


@pytest.mark.parametrize("auto_rig", [False, True])
@pytest.mark.parametrize("domain", ["uthana.com", "other.example.com"])
async def test_multipart_upload_and_save_contracts(auto_rig, domain):
    def respond(request):
        content = request.content.decode()
        if "multipart/form-data" in request.headers["content-type"]:
            assert '"0": ["variables.file"]' in content
            assert "fixture-bytes" in content
            if "create_video_to_motion(" in content:
                assert '"model": "video-to-motion-2.1"' in content
                return httpx.Response(200, json={"data": {"create_video_to_motion": {"job": {"id": "job1"}}}})
            assert f'"auto_rig": {str(auto_rig).lower()}' in content
            assert '"auto_rig_front_facing": true' in content
            assert '"include_fingers": true' in content
            return httpx.Response(200, json={"data": {"create_character": {"character": {"id": "character1"}}}})
        body = json.loads(content)
        if "upload_limits" in body["query"]:
            return httpx.Response(200, json={"data": {"org": {"upload_limits": None}}})
        assert body["variables"] == {
            "gltf": "{}",
            "motionName": "Saved",
            "sourceMotionId": "motion1",
            "characterId": "character1",
        }
        return httpx.Response(200, json={"data": {"create_motion_from_gltf": {"motion": {"id": "saved1"}}}})

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        assert (await api.video("walk.mp4", b"fixture-bytes", "Walk", "video-to-motion-2.1"))["job_id"] == "job1"
        assert (await api.upload_character("rig.fbx", b"fixture-bytes", "Rig", auto_rig))[
            "character_id"
        ] == "character1"
        assert (await api.save("{}", "Saved", "motion1", "character1"))["motion_id"] == "saved1"
    finally:
        await api.close()


@pytest.mark.parametrize("status", [302, 401, 500])
@pytest.mark.parametrize("domain", ["uthana.com", "other.example.com"])
async def test_errors_do_not_expose_body_or_follow_redirects(status, domain):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, text="secret-provider-detail", headers={"location": "https://elsewhere.invalid"})

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.job("job1")
        assert "secret" not in str(exc.value) and len(requests) == 1
    finally:
        await api.close()


async def test_partial_graphql_errors_never_count_as_success():
    api = UthanaAPI(
        "fake",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"data": {"job": {"id": "job1"}}, "errors": [{"message": "private-provider-detail"}]}
            )
        ),
    )
    try:
        with pytest.raises(APIError, match="GraphQL request failed"):
            await api.job("job1")
    finally:
        await api.close()


@pytest.mark.parametrize("domain", ["uthana.com", "other.example.com"])
async def test_catalog_usage_eligibility_and_export_effects_contracts(domain):
    seen = []

    def respond(request):
        seen.append(request)
        assert request.url.host == domain
        if request.url.path == "/graphql":
            body = json.loads(request.content)
            query = body["query"]
            assert query.lstrip().startswith("query") and "mutation" not in query
            if "motions_paged" in query:
                assert "label_search" not in query
                return httpx.Response(200, json={"data": {"motions_paged": {"items": [], "next_cursor": None}}})
            if "Usage" in query:
                assert "subscription { status secs_per_month characters }" in query
                assert "payg_prices { model_key billing_unit unit_price }" in query
                assert "payg_total_usd" in query
                assert "email" not in query and "users" not in query
                return httpx.Response(200, json={"data": {"org": {"payg_enabled": True}}})
            if "name" in query and "motion_download_secs_per_month" in query:
                return httpx.Response(200, json={"data": {"org": {"id": "o1", "name": "Studio"}}})
            if "upload_limits" in query:
                return httpx.Response(200, json={"data": {"org": {"upload_limits": None}}})
            assert "motion_download_allowed(motion_id: $motion_id, character_id: $character_id)" in query
            assert body["variables"] == {"motion_id": "m1", "character_id": "c1"}
            return httpx.Response(
                200, json={"data": {"motion_download_allowed": {"allowed": False, "reason": "Limit"}}}
            )
        assert request.url.path == "/motion/file/motion_viewer/c1/m1/fbx/c1-m1.fbx"
        assert dict(request.url.params) == {
            "fps": "30",
            "no_mesh": "false",
            "in_place": "true",
            "roblox_compatible": "false",
            "speed_multiplier": "0.5",
            "torso_only": "true",
        }
        return httpx.Response(200, content=b"export")

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        assert (await api.motions_page())["items"] == []
        assert (await api.usage())["org"]["payg_enabled"] is True
        assert (await api.download_allowed("m1", "c1"))["allowed"] is False
        await api.download("m1", "c1", "fbx", 30, True, True, False, 0.5, True)
        assert len(seen) == 6
    finally:
        await api.close()


@pytest.mark.parametrize("allowed", [None, "false"])
async def test_eligibility_null_is_unknown_and_strings_are_not_booleans(allowed):
    api = UthanaAPI(
        "fake",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"data": {"motion_download_allowed": {"allowed": allowed, "reason": None}}},
            )
        ),
    )
    try:
        if allowed is None:
            assert (await api.download_allowed("m1", "c1"))["allowed"] is None
        else:
            with pytest.raises(APIError, match="Invalid download eligibility"):
                await api.download_allowed("m1", "c1")
    finally:
        await api.close()


@pytest.mark.parametrize("is_confirmed", [True, False])
async def test_trial_limit_is_rejected_only_with_confirmed_generation_error(is_confirmed: bool) -> None:
    seen = []

    def respond(request):
        seen.append(request)
        envelope = (
            {
                "data": None,
                "errors": [
                    {
                        "type": "JobLimitExceeded",
                        "code": "job_limit_exceeded",
                        "path": ["create_text_to_motion_job"],
                        "message": "Wait for existing jobs.",
                    }
                ],
            }
            if is_confirmed
            else {"errors": [{"message": "rate limited"}]}
        )
        return httpx.Response(429, json=envelope)

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.generate("Walk", 4, "tar")
        assert exc.value.category == "rate_limit"
        assert exc.value.http_status == 429
        assert exc.value.outcome == ("rejected" if is_confirmed else "unknown")
        assert exc.value.details()["safe_to_resubmit"] is is_confirmed
        assert len(seen) == 1
        if is_confirmed:
            assert "Wait for existing jobs" in str(exc.value)
    finally:
        await api.close()


@pytest.mark.parametrize("status", ["RUNNING", "FINISHED", "FAILED"])
async def test_job_discovery_uses_sdk_and_preserves_scope(status):
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            json={
                "data": {
                    "jobs": [
                        {
                            "id": "j1",
                            "status": status,
                            "method": "TextToMotion",
                            "created_at": "2026-01-01T00:00:00Z",
                            "started_at": None,
                            "ended_at": None,
                        }
                    ]
                }
            },
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        result = await api.jobs("TextToMotion")
    finally:
        await api.close()
    job = result["jobs"][0]
    assert job["job_id"] == "j1" and job["motion_id"] is None
    assert job["created"] == "2026-01-01T00:00:00Z" and job["started"] is None
    assert job["provider_status"] == status
    assert job["state"] == {"RUNNING": "pending", "FINISHED": "unresolved", "FAILED": "failed"}[status]
    assert seen[0]["variables"] == {"method": "TextToMotion"}
    assert "query ListJobs" in seen[0]["query"]
    assert "24 hours" in result["scope_note"]


async def test_empty_job_discovery():
    api = UthanaAPI(
        "fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"jobs": []}}))
    )
    try:
        assert (await api.jobs())["jobs"] == []
    finally:
        await api.close()


@pytest.mark.parametrize("rows", [[None], [{"id": "j1", "status": {"bad": True}}]])
async def test_job_discovery_rejects_invalid_records(rows):
    api = UthanaAPI(
        "fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"jobs": rows}}))
    )
    try:
        with pytest.raises(APIError):
            await api.jobs()
    finally:
        await api.close()


async def test_job_discovery_preserves_permission_error():
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    try:
        with pytest.raises(APIError) as failure:
            await api.jobs()
        assert failure.value.category == "permission"
    finally:
        await api.close()


@pytest.mark.parametrize("owner,source", [("org1", "organization"), ("builtins", "other_accessible")])
async def test_character_inspection_uses_sdk_and_reports_ownership(owner, source):
    def respond(request):
        query = json.loads(request.content)["query"]
        if "GetCharacter" in query:
            data = {
                "character": {
                    "id": "c1",
                    "name": "Alex",
                    "org_id": owner,
                    "created": "2026-01-01T00:00:00Z",
                    "updated": {},
                    "deleted": None,
                }
            }
        else:
            data = {"org": {"id": "org1"}}
        return httpx.Response(200, json={"data": data})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        result = await api.character("c1")
    finally:
        await api.close()
    assert result["character_id"] == "c1" and result["name"] == "Alex"
    assert result["source"] == source and result["org_id"] == owner
    assert result["created"] == "2026-01-01T00:00:00Z" and result["updated"] is None


@pytest.mark.parametrize("status", [403, 404])
async def test_character_inspection_preserves_access_errors(status):
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda request: httpx.Response(status)))
    try:
        with pytest.raises(APIError) as failure:
            await api.character("c1")
        assert failure.value.category == {403: "permission", 404: "not_found"}[status]
    finally:
        await api.close()


@pytest.mark.parametrize(
    "row", [None, {"id": "other", "name": "Alex", "org_id": "org1"}, {"id": "c1", "name": {}, "org_id": "org1"}]
)
async def test_character_inspection_rejects_missing_or_invalid_records(row):
    api = UthanaAPI(
        "fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"character": row}}))
    )
    try:
        with pytest.raises(APIError):
            await api.character("c1")
    finally:
        await api.close()


async def test_usage_combines_published_sdk_usage_and_identity_reads():
    queries = []

    def respond(request):
        query = json.loads(request.content)["query"]
        queries.append(query)
        data = (
            {"org": {"payg_enabled": True, "payg_total_usd": "12.50"}, "subscription": None}
            if "query Usage" in query
            else {"org": {"id": "org1", "name": "Studio"}}
        )
        return httpx.Response(200, json={"data": data})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        data = await api.usage()
    finally:
        await api.close()
    assert data["org"] == {
        "video_upload_max_bytes": None,
        "id": "org1",
        "name": "Studio",
        "payg_enabled": True,
        "payg_total_usd": "12.50",
    }
    assert len(queries) == 3 and all("mutation" not in query for query in queries)


@pytest.mark.parametrize("failure", ["timeout", 403, 500, "malformed"])
async def test_usage_preserves_balances_when_optional_identity_is_unavailable(failure: str | int) -> None:
    queries = []

    def respond(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["query"]
        queries.append(query)
        if "query Usage" in query:
            return httpx.Response(200, json={"data": {"org": {"payg_enabled": True, "payg_total_usd": "12.50"}}})
        if failure == "timeout":
            raise httpx.ReadTimeout("Identity lookup timed out")
        if failure == "malformed":
            return httpx.Response(200, json={"data": {"org": {"id": []}}})
        return httpx.Response(failure, json={"error": "Identity unavailable"})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        data = await api.usage()
    finally:
        await api.close()
    assert data["org"] == {
        "video_upload_max_bytes": None,
        "payg_enabled": True,
        "payg_total_usd": "12.50",
        "id": None,
        "name": None,
    }
    assert len(queries) == 3 and all("mutation" not in query for query in queries)


async def test_usage_does_not_hide_unexpected_identity_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_identity() -> None:
        raise RuntimeError("Unexpected bug")

    api = UthanaAPI(
        "fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"org": {}}}))
    )
    monkeypatch.setattr(api, "org", broken_identity)
    try:
        with pytest.raises(RuntimeError, match="Unexpected bug"):
            await api.usage()
    finally:
        await api.close()


@pytest.mark.parametrize("body", [b"secret-provider-detail", b'{"data":null}'])
async def test_uncertain_sdk_mutation_results_are_not_misreported_as_size_errors(body: bytes) -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=body)

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as error:
            await api.generate("walk", 4, "character1")
    finally:
        await api.close()
    assert error.value.outcome == "unknown" and error.value.category == "provider_error"
    assert "confirm" in str(error.value) and "size" not in str(error.value) and "secret" not in str(error.value)
    assert len(requests) == 1
