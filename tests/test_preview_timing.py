import io

import pytest
from fakes import FakeAPI
from PIL import Image

from uthana_mcp.operations import Operations


def animation(durations, *, default_image=False):
    frames = [Image.new("RGBA", (8, 8), color) for color in ("red", "green", "blue")]
    if default_image:
        frames.insert(0, Image.new("RGBA", (8, 8), "black"))
    output = io.BytesIO()
    frames[0].save(
        output,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        default_image=default_image,
        loop=0,
    )
    return output.getvalue()


def timing(data):
    with Image.open(io.BytesIO(data)) as img:
        return Operations.preview_timing(img)


def cached(ops, data, frame_count=3):
    # Reproduce receipts written before timing availability was validated.
    return ops.store.artifact(
        data,
        ".png",
        {
            "format": "apng",
            "motion_id": "motion1",
            "character_id": "character1",
            "frame_count": frame_count,
            "frame_times_seconds": [0] * frame_count,
            "preview_duration_seconds": 0,
        },
    )


@pytest.mark.parametrize("delays", [[0, 0, 0], [100, 0, 200], [100, 200, 0]])
async def test_zero_or_partially_missing_animation_delays_are_unavailable(tmp_path, delays):
    data = animation(delays)
    api = FakeAPI()

    async def preview(*args):
        return data

    api.preview = preview
    ops = Operations(api, tmp_path)
    result = await ops.preview("motion1")
    assert result["animated"] and result["frame_count"] == 3
    assert result["timing_status"] == "unavailable"
    assert result["frame_times_seconds"] == [None, None, None]
    assert result["preview_duration_seconds"] is None
    image, metadata = ops.preview_frame(result["artifact_id"], 2)
    assert metadata["frame_index"] == 2 and metadata["frame_count"] == 3
    assert metadata["time_seconds"] is None and metadata["timing_status"] == "unavailable"
    assert Image.open(io.BytesIO(image)).getpixel((0, 0)) == (0, 0, 255, 255)


@pytest.mark.parametrize("default_image", [False, True])
def test_valid_variable_delays_and_default_image_keep_actual_timing(tmp_path, default_image):
    data = animation([17, 231, 402], default_image=default_image)
    result = timing(data)
    assert result["frame_count"] == 3 and result["default_image_excluded"] is default_image
    assert result["frame_times_seconds"] == [0, 0.017, 0.248]
    assert result["preview_duration_seconds"] == pytest.approx(0.650)
    assert result["timing_status"] == "available"
    ops = Operations(FakeAPI(), tmp_path)
    # Cached timestamps are deliberately wrong; extraction must use the actual bytes.
    artifact = cached(ops, data)
    first, first_metadata = ops.preview_frame(artifact["artifact_id"], 0)
    last, last_metadata = ops.preview_frame(artifact["artifact_id"], 2)
    assert first_metadata["time_seconds"] == 0
    assert last_metadata["time_seconds"] == 0.248 and last_metadata["timing_status"] == "available"
    assert Image.open(io.BytesIO(first)).getpixel((0, 0)) == (255, 0, 0, 255)
    assert Image.open(io.BytesIO(last)).getpixel((0, 0)) == (0, 0, 255, 255)
    with pytest.raises(ValueError, match="outside this preview"):
        ops.preview_frame(artifact["artifact_id"], 3)


def test_old_cached_zero_times_never_label_newly_extracted_frames(tmp_path):
    ops = Operations(FakeAPI(), tmp_path)
    artifact = cached(ops, animation([0, 0, 0]), frame_count=100)
    _, metadata = ops.preview_frame(artifact["artifact_id"], 1)
    assert metadata["time_seconds"] is None and metadata["timing_status"] == "unavailable"
    assert metadata["frame_count"] == 3
    with pytest.raises(ValueError, match="outside this preview"):
        ops.preview_frame(artifact["artifact_id"], 3)


def test_static_png_without_delay_has_no_invented_duration():
    output = io.BytesIO()
    Image.new("RGBA", (8, 8), "red").save(output, format="PNG")
    result = timing(output.getvalue())
    assert not result["animated"] and result["frame_count"] == 1
    assert result["timing_status"] == "unavailable"
    assert result["frame_times_seconds"] == [None] and result["preview_duration_seconds"] is None


@pytest.mark.parametrize("duration", [None, -1, float("nan"), float("inf"), "100", True, 60_001])
def test_unusable_decoder_delay_does_not_become_a_timestamp(duration):
    class DecodedFrames:
        width = height = 8
        n_frames = 2
        info = {}

        def seek(self, index):
            self.info = {"duration": 100 if index == 0 else duration}

    result = Operations.preview_timing(DecodedFrames())
    assert result["frame_count"] == 2 and result["timing_status"] == "unavailable"
    assert result["frame_times_seconds"] == [None, None] and result["preview_duration_seconds"] is None
