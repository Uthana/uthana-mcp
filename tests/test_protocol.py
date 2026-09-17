import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import uthana_mcp


def structured(result):
    assert not result.isError, result
    return result.structuredContent


async def test_real_stdio_discovery_and_generation_trim_review_export(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("stdio_fixture.py")), str(tmp_path)],
        # MCP filters inherited environment variables, including PYTHONPATH.
        env={"PYTHONPATH": str(Path(uthana_mcp.__file__).resolve().parent.parent)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            catalog = await client.list_tools()
            tools = {tool.name: tool for tool in catalog.tools}
            assert set(tools) == {
                "generate_motion",
                "generate_motion_v2",
                "generate_locomotion",
                "list_locomotion_styles",
                "estimate_model_cost",
                "get_job",
                "get_motion",
                "get_request_status",
                "trim_motion",
                "get_preview",
                "get_preview_frame",
                "generate_motion_from_video",
                "upload_character",
                "create_character_from_image",
                "create_looped_motion",
                "create_stitched_motion",
                "list_characters",
                "list_motions",
                "get_usage",
                "check_download_allowed",
                "save_motion",
                "download_motion",
            }
            assert "source_duration_seconds" not in tools["trim_motion"].inputSchema["properties"]
            assert tools["download_motion"].annotations.readOnlyHint is False
            for tool in ("list_motions", "get_usage", "check_download_allowed"):
                assert tools[tool].annotations.readOnlyHint is True
            speed = tools["download_motion"].inputSchema["properties"]["speed_multiplier"]
            assert speed["exclusiveMinimum"] == 0 and speed["maximum"] == 2
            catalog_result = structured(await client.call_tool("list_motions", {"query": "WALK", "limit": 1}))
            assert catalog_result["motions"][0]["source"] == "organization"
            assert catalog_result["next_offset"] == 1 and not catalog_result["full_library_searched"]
            usage = structured(await client.call_tool("get_usage", {}))
            assert usage["monthly_downloads"]["remaining"] == 15
            eligibility = structured(await client.call_tool("check_download_allowed", {"motion_id": "denied"}))
            assert eligibility["allowed"] is False and eligibility["reserves_allowance"] is False
            estimate = structured(
                await client.call_tool("estimate_model_cost", {"model": "text-to-motion-2.0", "quantity": 4})
            )
            assert estimate["estimated_cost_usd"] == "0.1200" and estimate["actual_cost_usd"] is None
            v2 = structured(await client.call_tool("generate_motion_v2", {"request_id": "v2", "prompt": "Walk"}))
            assert v2["motion_id"] == "motion1" and "job_id" not in v2
            styles = structured(await client.call_tool("list_locomotion_styles", {}))
            loco = structured(
                await client.call_tool("generate_locomotion", {"request_id": "loco", "style_id": styles["styles"][0]})
            )
            assert loco["loop_intended"] and loco["review_status"] == "unreviewed"
            resources = await client.list_resources()
            assert any(str(resource.uri) == "uthana://workflow" for resource in resources.resources)
            workflow = await client.read_resource("uthana://workflow")
            assert "Do not execute those suggestions" in workflow.contents[0].text
            prompts = await client.list_prompts()
            assert any(prompt.name == "review_motion" for prompt in prompts.prompts)
            prompt = await client.get_prompt("review_motion", {"original_prompt": "Jump", "motion_id": "motion1"})
            assert "Do not execute" in prompt.messages[0].content.text
            generated = structured(await client.call_tool("generate_motion", {"request_id": "gen1", "prompt": "Jump"}))
            assert generated["job_id"] == "job1"
            status = structured(await client.call_tool("get_job", {"job_id": generated["job_id"]}))
            assert status["motion_id"] == "motion1"
            trimmed = structured(
                await client.call_tool(
                    "trim_motion",
                    {
                        "request_id": "trim1",
                        "motion_id": "motion1",
                        "start_seconds": 1,
                        "end_seconds": 3,
                        "name": "Middle",
                    },
                )
            )
            assert trimmed["verification_status"] == "verified_metadata"
            preview = structured(await client.call_tool("get_preview", {"motion_id": trimmed["motion_id"]}))
            frame = await client.call_tool(
                "get_preview_frame", {"artifact_id": preview["artifact_id"], "frame_index": 1}
            )
            assert not frame.isError and frame.content[1].type == "image"
            assert json.loads(frame.content[0].text)["time_seconds"] == 0.1
            exported = structured(
                await client.call_tool(
                    "download_motion",
                    {
                        "request_id": "export1",
                        "motion_id": trimmed["motion_id"],
                        "format": "fbx",
                        "fps": 30,
                        "include_mesh": True,
                        "speed_multiplier": 0.5,
                        "torso_only": True,
                    },
                )
            )
            recovered = structured(await client.call_tool("get_request_status", {"request_id": "export1"}))
            assert recovered["artifact_status"] == "verified_local_bytes"
            assert exported["speed_multiplier"] == 0.5 and exported["torso_only"] is True
            assert Path(exported["local_path"]).read_bytes() == b"offline-export-fixture"
            invalid = await client.call_tool(
                "trim_motion",
                {"request_id": "bad", "motion_id": "motion1", "start_seconds": 0, "end_seconds": 10, "name": "Bad"},
            )
            assert invalid.isError
            for values in ({"speed_multiplier": True}, {"speed_multiplier": 0}, {"torso_only": "false"}):
                bad = await client.call_tool(
                    "download_motion", {"request_id": "badexport", "motion_id": "motion1", **values}
                )
                assert bad.isError


@pytest.mark.parametrize("domain", ["staging.uthana.com", "uthana.com"])
async def test_actual_entrypoint_discovers_without_credentials(domain):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "uthana_mcp.server"],
        env={
            "UTHANA_API_KEY": "",
            "UTHANA_DOMAIN": domain,
            "PYTHONPATH": str(Path(uthana_mcp.__file__).resolve().parent.parent),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            initialized = await client.initialize()
            assert domain in initialized.instructions
            workflow = await client.read_resource("uthana://workflow")
            assert domain in workflow.contents[0].text.splitlines()[0]
            assert len((await client.list_tools()).tools) == 22
            result = await client.call_tool("get_job", {"job_id": "job1"})
            assert result.isError and "UTHANA_API_KEY" in result.content[0].text
