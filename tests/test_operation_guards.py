import io

import pytest
from fakes import FakeAPI
from PIL import Image

from uthana_mcp.operations import Operations


@pytest.fixture
def setup(tmp_path):
    api = FakeAPI()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    return api, Operations(api, tmp_path / "state", inputs), inputs


async def test_locomotion_styles_reject_a_non_list(setup):
    api, ops, _inputs = setup

    async def styles():
        return {"neutral": True}

    api.locomotion_styles = styles
    with pytest.raises(ValueError, match="Locomotion styles unavailable"):
        await ops.locomotion_styles()


async def test_estimate_rejects_an_unknown_model(setup):
    _api, ops, _inputs = setup
    with pytest.raises(ValueError, match="model must be one of"):
        await ops.estimate_cost("not-a-model", 1)


async def test_uploads_reject_missing_directory_bad_type_and_empty_files(setup, tmp_path):
    api, ops, inputs = setup
    bare = Operations(api, tmp_path / "other-state")
    with pytest.raises(ValueError, match="UTHANA_MCP_INPUT_DIR"):
        bare.read_input("clip.mp4", {".mp4"})
    notes = inputs / "notes.txt"
    notes.write_bytes(b"hello")
    with pytest.raises(ValueError, match="file_path must use"):
        ops.read_input(str(notes), {".mp4", ".mov", ".webm"})
    empty = inputs / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="1 byte"):
        ops.read_input(str(empty), {".mp4"})
    with pytest.raises(ValueError, match="video-to-motion"):
        await ops.video("vid1", str(empty), "Clip", model="other")
    with pytest.raises(ValueError, match="auto_rig must be a boolean"):
        await ops.upload_character("char1", str(empty), "Tar", auto_rig="yes")


async def test_preview_rejects_bad_format_and_bytes(setup):
    api, ops, _inputs = setup
    with pytest.raises(ValueError, match="Preview format"):
        await ops.preview("motion1", format="gif")

    async def jpeg(*_args):
        output = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(output, format="JPEG")
        return output.getvalue()

    api.preview = jpeg
    with pytest.raises(ValueError, match="PNG/APNG"):
        await ops.preview("motion1", format="apng")

    async def not_webm(*_args):
        return b"not-a-webm"

    api.preview = not_webm
    with pytest.raises(ValueError, match="WebM"):
        await ops.preview("motion1", format="webm")


async def test_download_rejects_an_empty_asset(setup):
    api, ops, _inputs = setup

    async def empty(**_args):
        return b""

    api.download = empty
    # An empty body is raised inside the mutation, so the receipt stays unconfirmed.
    with pytest.raises(RuntimeError, match="unconfirmed"):
        await ops.download("export1", "motion1")


async def test_save_rejects_oversized_and_non_animated_gltf(setup):
    _api, ops, inputs = setup
    huge = inputs / "huge.gltf"
    huge.write_bytes(b"{" + b" " * (16 * 1024 * 1024))
    with pytest.raises(ValueError, match="16 MiB"):
        await ops.save("save-huge", str(huge), "motion1", "mixamo1", "Edited")
    broken = inputs / "broken.gltf"
    broken.write_bytes(b"{")
    with pytest.raises(ValueError, match="self-contained GLTF JSON"):
        await ops.save("save-broken", str(broken), "motion1", "mixamo1", "Edited")
    still = inputs / "still.gltf"
    still.write_text('{"asset": {"version": "2.0"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="animated GLTF 2.0"):
        await ops.save("save-still", str(still), "motion1", "mixamo1", "Edited")


async def test_stitch_prompt_and_character_query_limits(setup):
    _api, ops, _inputs = setup
    with pytest.raises(ValueError, match="Stitch prompt"):
        await ops.stitch("stitch1", {}, {}, prompt="x" * 1001)
    with pytest.raises(ValueError, match="query must be text"):
        await ops.characters(query="x" * 201)
