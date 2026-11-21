import json

import httpx
import pytest

from uthana_mcp.api import APIError, UthanaAPI


@pytest.mark.parametrize("size,limit,should_reject", [(4, 4, False), (5, 4, True), (5, None, False)])
async def test_account_video_limit_precedes_submission(size: int, limit: int | None, should_reject: bool) -> None:
    submissions = []

    def respond(request: httpx.Request) -> httpx.Response:
        if "multipart/form-data" in request.headers["content-type"]:
            submissions.append(request)
            return httpx.Response(200, json={"data": {"create_video_to_motion": {"job": {"id": "job1"}}}})
        assert "upload_limits" in json.loads(request.content)["query"]
        return httpx.Response(
            200, json={"data": {"org": {"upload_limits": [{"category": "video", "max_bytes": limit}]}}}
        )

    api = UthanaAPI("fake", "uthana.com", transport=httpx.MockTransport(respond))
    try:
        if should_reject:
            with pytest.raises(APIError, match="Choose a smaller video") as error:
                await api.video("clip.mp4", b"x" * size, "Clip", "video-to-motion-3.0")
            assert error.value.outcome == "rejected"
        else:
            assert (await api.video("clip.mp4", b"x" * size, "Clip", "video-to-motion-3.0"))["job_id"] == "job1"
        assert len(submissions) == (0 if should_reject else 1)
    finally:
        await api.close()


@pytest.mark.parametrize("limit", [True, -1, 0, "50"])
async def test_invalid_limit_rejects_without_submitting(limit: object) -> None:
    submissions = []

    def respond(request: httpx.Request) -> httpx.Response:
        submissions.append(request)
        return httpx.Response(
            200, json={"data": {"org": {"upload_limits": [{"category": "video", "max_bytes": limit}]}}}
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as error:
            await api.video("clip.mp4", b"video", "Clip", "video-to-motion-3.0")
        assert error.value.outcome == "rejected"
        assert len(submissions) == 1
    finally:
        await api.close()
