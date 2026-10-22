"""Host-independent Uthana operations; reusable without importing MCP."""

import hashlib
import io
import json
import os
import stat
import time
import warnings
from pathlib import Path

import httpx
from PIL import Image

from .billing import PUBLISHED_MODELS, estimate_cost, receipt_billing
from .catalog import catalog_filters, motion_page, page_bounds, usage_snapshot
from .errors import APIError
from .safe_open import open_nofollow
from .stitching import AutoStitchOptions, StitchClip, api_clip
from .store import Store
from .validation import TAR, identifier, number, text

MAX_UPLOAD_BYTES = 128 * 1024 * 1024


class Operations:
    def __init__(self, api, directory, input_directory=None):
        self.api = api
        self.store = Store(Path(directory), api.scope)
        self.input_directory = Path(input_directory).expanduser().resolve() if input_directory else None

    async def generate(self, request_id, prompt, duration_seconds=4, character_id=TAR):
        args = {
            "prompt": text(prompt, 1000),
            "duration_seconds": number(duration_seconds, 4, 10),
            "character_id": identifier(character_id),
        }
        # Recover historical receipts outside the current input contract through get_request_status.
        if duration_seconds != int(duration_seconds):
            raise ValueError("V3 duration must be a whole number of seconds from 4 to 10; it is not rounded silently")
        return await self.store.mutation(request_id, "generate", args, lambda: self.api.generate(**args))

    async def generate_v2(self, request_id, prompt, duration_seconds=4, character_id=TAR):
        args = {
            "prompt": text(prompt, 1000),
            "duration_seconds": number(duration_seconds, 4, 10),
            "character_id": identifier(character_id),
        }
        # V2's 20 FPS model expects multiples of eight frames (0.4 seconds).
        frames = args["duration_seconds"] * 20
        if abs(frames / 8 - round(frames / 8)) > 1e-8:
            raise ValueError("V2 duration must use 0.4-second increments from 4 to 10 seconds")
        return await self.store.mutation(request_id, "generate_v2", args, lambda: self.api.generate_v2(**args))

    async def locomotion_styles(self):
        styles = await self.api.locomotion_styles()
        if not isinstance(styles, list) or not all(isinstance(s, str) and s.strip() for s in styles):
            raise ValueError("Locomotion styles unavailable from Uthana. Retry the read later.")
        return {"styles": styles}

    async def locomotion(
        self, request_id, character_id=TAR, strides=4, move_speed=1.2, style_id="neutral_male_a", travel_angle=0
    ):
        identifier(character_id)
        if isinstance(strides, bool) or not isinstance(strides, int) or not 1 <= strides <= 5:
            raise ValueError("strides must be an integer from 1 to 5")
        args = {
            "character_id": character_id,
            "strides": strides,
            "move_speed": number(move_speed, 0.25, 8),
            "style_id": text(style_id, 100),
            "travel_angle": number(travel_angle, -180, 180),
        }
        args["style_id"] = args["style_id"].strip()
        # Preflight a new request only; an existing receipt must recover even if style discovery is down.
        if self.store.get_request(request_id)["state"] == "not_found":
            styles = (await self.locomotion_styles())["styles"]
            if args["style_id"].casefold() not in {style.casefold() for style in styles}:
                raise ValueError("Unknown locomotion style; use list_locomotion_styles")

        async def invoke():
            result = await self.api.locomotion(**args)
            return {
                **result,
                "loop_intended": True,
                "review_status": "unreviewed",
                "timing_note": "Duration follows stride count, speed, and generated contacts; inspect native metadata.",
            }

        return await self.store.mutation(request_id, "locomotion", args, invoke)

    async def estimate_cost(self, model, quantity):
        # Validation precedes the read, and no generation or billing mutation is performed.
        if model not in PUBLISHED_MODELS:
            raise ValueError("model must be one of: " + ", ".join(sorted(PUBLISHED_MODELS)))
        number(quantity, 0, 3600)
        return estimate_cost(await self.api.prices(), model, quantity)

    async def trim(self, request_id, motion_id, start_seconds, end_seconds, name):
        identifier(motion_id)
        text(name)
        number(start_seconds, 0, 1e9)
        number(end_seconds, 0, 1e9)
        # Completed retries use the historical source to reconstruct the original fingerprint.
        completed = self.store.completed(request_id, "trim")
        source = completed["source"] if completed else await self.api.motion(motion_id)
        duration = source["duration_seconds"]
        if not 0 <= start_seconds < end_seconds <= duration:
            raise ValueError(
                f"start_seconds must be >= 0 and less than end_seconds; end_seconds must be at most {duration:.3f} seconds (received {start_seconds}, {end_seconds})"
            )
        start, end = start_seconds / duration, end_seconds / duration
        start_frame, end_frame = int(start * source["frame_count"]), int(end * source["frame_count"])
        if start_frame == end_frame:
            raise ValueError("Selected interval is shorter than one native frame; choose a larger interval")
        # SkeletonState.clip includes end_frame; a normalized end of 1 is clamped by slicing.
        last_frame = min(end_frame, source["frame_count"] - 1)
        args = {
            "motion_id": motion_id,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "name": name,
            "source_bundle_id": source["bundle_id"],
            "source_bundle_sha256": source["bundle_sha256"],
        }

        if completed:
            return self.recovered_saved(self.store.replay(request_id, "trim", args))

        async def invoke():
            result = await self.api.trim(motion_id, start, end, name)
            return {
                **result,
                "source_motion_id": motion_id,
                "source": source,
                "requested_interval_seconds": [start_seconds, end_seconds],
                "native_frame_interval": [start_frame, last_frame],
                "frame_interval_end_inclusive": True,
                "loop": False,
                "expected_frame_count": last_frame - start_frame + 1,
                "review_status": "unreviewed",
            }

        receipt = await self.store.mutation(request_id, "trim", args, invoke)
        return await self.verify_saved(receipt)

    @staticmethod
    def recovered_saved(result):
        return {
            **result,
            "verification_status": "not_rechecked",
            "verification_note": "Recovered the confirmed historical result locally; native metadata and visual quality were not rechecked.",
        }

    def recover_request(self, request_id):
        """Recover IDs and cached exports without input files or any upstream dependency."""
        status = self.store.get_request(request_id)
        result = status.get("result")
        if status.get("operation") == "upload_character" and status["state"] in {"pending", "unknown"}:
            status["inspection"] = (status.get("progress") or {}).get(
                "inspection",
                {
                    "tool": "list_characters",
                    "arguments": {"query": "", "limit": 50},
                },
            )
            status["next_action"] = (
                "Inspect list_characters using the original upload name. A name match is only a candidate; verify it in Uthana. Contact support with the request ID if unresolved."
            )
        if result and result.get("job_id"):
            status["job_status_note"] = "Submission status is historical; use get_job for the current job state."
        if status["state"] != "complete" or not isinstance(result, dict):
            return status
        status["result"] = {**result, "replayed": True}
        if status["operation"] in {"trim", "save", "loop", "stitch"}:
            status["result"] = self.recovered_saved(status["result"])
        if result.get("artifact_id"):
            try:
                self.store.read_artifact(result["artifact_id"])
                status["artifact_status"] = "verified_local_bytes"
            except (OSError, ValueError):
                status["artifact_status"] = "unavailable_or_changed"
                status["next_action"] = (
                    "Recover the original cached file; no replacement was downloaded. Known IDs remain in result."
                )
        return status

    def record_saved_verification(self, result):
        observation = {"status": result["verification_status"], "checked_at_unix": time.time()}
        for field in ("error", "errors"):
            if "verification_" + field in result:
                observation[field] = result["verification_" + field]
        history = self.store.record_verification(result["request_id"], observation)
        return {**result, **history}

    async def verify_saved(self, receipt):
        # The new ID is already durable even if metadata lookup fails after a successful mutation.
        result = {**receipt, "verification_status": "unverified"}
        for field in ("verification_error", "verification_errors", "verification_note", "saved"):
            result.pop(field, None)
        originals = receipt.get("sources", [receipt["source"]])
        if receipt["motion_id"] in {source["motion_id"] for source in originals}:
            return self.record_saved_verification(
                {**result, "verification_status": "failed", "verification_error": "Source ID was returned as result"}
            )
        try:
            saved = await self.api.motion(receipt["motion_id"])
            sources = [await self.api.motion(original["motion_id"]) for original in originals]
        except Exception:
            return self.record_saved_verification(
                {
                    **result,
                    "verification_error": "Metadata unavailable; recover these IDs without repeating the mutation",
                }
            )
        original = receipt["source"]
        errors = []
        for source, prior in zip(sources, originals):
            if (source["bundle_id"], source["bundle_sha256"]) != (prior["bundle_id"], prior["bundle_sha256"]):
                errors.append("Source bundle identity changed")
        if saved["bundle_id"] in {prior["bundle_id"] for prior in originals}:
            errors.append("Result does not have its own bundle")
        if "expected_frame_count" in receipt:
            if saved["frame_count"] != receipt["expected_frame_count"] or saved["fps"] != original["fps"]:
                errors.append("Saved trim timing disagrees with requested native frame interval")
        return self.record_saved_verification(
            {
                **result,
                "saved": saved,
                "verification_status": "failed" if errors else "verified_metadata",
                "verification_errors": errors,
            }
        )

    def read_input(self, filename, extensions, max_bytes=MAX_UPLOAD_BYTES):
        if self.input_directory is None:
            raise ValueError("Configure UTHANA_MCP_INPUT_DIR to enable local-file uploads")
        try:
            path = Path(filename).expanduser().resolve(strict=True)
            if not path.is_relative_to(self.input_directory):
                raise ValueError("file_path must be inside UTHANA_MCP_INPUT_DIR")
            if path.suffix.lower() not in extensions:
                formats = ", ".join(sorted(extensions))
                detail = "; .gltf means self-contained JSON, not binary .glb" if extensions == {".gltf"} else ""
                raise ValueError(f"file_path must use {formats} inside UTHANA_MCP_INPUT_DIR{detail}")
            # Open without following a final symlink; read a bounded snapshot used for both hashing and upload.
            fd = open_nofollow(path)
            with os.fdopen(fd, "rb") as f:
                info = os.fstat(f.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
                    raise ValueError(f"Upload must be a regular file no larger than {max_bytes // (1024 * 1024)} MiB")
                data = f.read(max_bytes + 1)
            if not data or len(data) > max_bytes:
                raise ValueError(f"Upload must contain 1 byte to {max_bytes // (1024 * 1024)} MiB")
        except (OSError, RuntimeError):
            raise ValueError(
                "file_path must name a readable regular file inside UTHANA_MCP_INPUT_DIR on the MCP server"
            ) from None
        return path.name, data, hashlib.sha256(data).hexdigest()

    async def video(self, request_id, file_path, name, model="video-to-motion-2.0"):
        text(name)
        if model not in {"video-to-motion-2.0", "video-to-motion-2.1"}:
            raise ValueError("Choose video-to-motion-2.0 or video-to-motion-2.1")
        filename, data, digest = self.read_input(file_path, {".mp4", ".mov", ".webm"})
        args = {"content_sha256": digest, "filename": filename, "name": name, "model": model}
        return await self.store.mutation(request_id, "video", args, lambda: self.api.video(filename, data, name, model))

    async def upload_character(
        self,
        request_id,
        file_path,
        name,
        auto_rig=False,
        front_facing=True,
        include_fingers=True,
        rerig_target=None,
    ):
        text(name)
        invalid_rigging_switches = not all(
            isinstance(value, bool) for value in (auto_rig, front_facing, include_fingers)
        )
        if invalid_rigging_switches:
            raise ValueError("auto_rig, front_facing, and include_fingers must be booleans")
        if rerig_target not in (None, "r15", "ue5"):
            raise ValueError("Choose rerig_target r15 or ue5, or omit it to keep the original skeleton")
        filename, data, digest = self.read_input(file_path, {".fbx", ".glb"}, 30 * 1024 * 1024)
        args = {"content_sha256": digest, "filename": filename, "name": name, "auto_rig": auto_rig}

        # Omit new default options from the fingerprint so pre-expansion receipts still replay.
        if not front_facing:
            args["front_facing"] = False
        if not include_fingers:
            args["include_fingers"] = False
        if rerig_target is not None:
            args["rerig_target"] = rerig_target

        async def invoke():
            self.store.record_progress(
                request_id,
                "upload_character",
                {
                    "stage": "upload_requested",
                    "name": name,
                    "content_sha256": digest,
                    "inspection": {"tool": "list_characters", "arguments": {"query": name, "limit": 50}},
                },
            )
            return await self.api.upload_character(
                filename, data, name, auto_rig, front_facing, include_fingers, rerig_target
            )

        return await self.store.mutation(request_id, "upload_character", args, invoke)

    async def create_character_from_image(self, request_id, file_path, name, include_fingers=True):
        text(name)
        if not isinstance(include_fingers, bool):
            raise ValueError("include_fingers must be a boolean")
        filename, data, digest = self.read_input(file_path, {".png", ".jpg", ".jpeg"}, 16 * 1024 * 1024)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    expected = "PNG" if Path(filename).suffix.lower() == ".png" else "JPEG"
                    if image.format != expected or image.width * image.height > 16_000_000:
                        raise ValueError("Choose a PNG/JPEG image no larger than 16 megapixels")
                    if getattr(image, "n_frames", 1) != 1:
                        raise ValueError("Choose a single-frame reference image")
                    image.verify()
        except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ValueError("Choose a valid PNG/JPEG reference image") from error
        args = {"filename": filename, "content_sha256": digest, "name": name}
        # Omit the new default option from the fingerprint so pre-expansion receipts still replay.
        if not include_fingers:
            args["include_fingers"] = False

        async def invoke():
            # A confirmed rejection in finalization can retry that stage without
            # creating a second preview/character. Unknown outcomes remain blocked.
            prepared = self.store.get_request(request_id).get("progress")
            if prepared is None:
                prepared = await self.api.prepare_character_image(filename, data)
                self.store.record_progress(request_id, "character_from_image", prepared)
            result = await self.api.finalize_character_image(prepared, name, include_fingers)
            return {
                **result,
                "name": name,
                "source_image_sha256": digest,
                "review_status": "unreviewed",
                "stage": "character_created",
            }

        return await self.store.mutation(request_id, "character_from_image", args, invoke)

    async def preview_character_from_prompt(self, request_id, prompt):
        text(prompt, 1000)
        args = {"prompt": prompt}

        async def invoke():
            prepared = await self.api.preview_character_prompt(prompt)
            # Persist the character ID before fetching images, so an interrupted fetch never hides it.
            self.store.record_progress(
                request_id, "character_prompt_preview", {"character_id": prepared["character_id"]}
            )
            previews = []
            for index, preview in enumerate(prepared["previews"]):
                entry = {"preview_index": index, "image_key": preview["image_key"]}
                try:
                    if not preview["url"]:
                        raise ValueError("Uthana returned no preview URL")
                    data = await self.api.fetch_preview_image(preview["url"])
                    with Image.open(io.BytesIO(data)) as image:
                        if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 16_000_000:
                            raise ValueError("Preview is not a supported still image")
                        suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image.format]
                        mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image.format]
                        entry.update({"width": image.width, "height": image.height})
                    saved = self.store.artifact(
                        data,
                        suffix,
                        {
                            "character_id": prepared["character_id"],
                            "preview_index": index,
                            "format": "character_preview",
                            "mime_type": mime,
                        },
                    )
                    entry.update(
                        {"artifact_id": saved["artifact_id"], "local_path": saved["local_path"], "mime_type": mime}
                    )
                except (APIError, OSError, ValueError, httpx.HTTPError):
                    # The character ID is still usable; a missing image only limits review.
                    entry["image_unavailable"] = "Preview image unavailable; inspect the character in Uthana."
                previews.append(entry)
            return {
                "stage": "previews_ready",
                "character_id": prepared["character_id"],
                "prompt": prompt,
                "previews": previews,
                "review_status": "unreviewed",
                "next_step": "Show the previews to the user. After they choose one, call "
                "create_character_from_prompt with this request_id as preview_request_id and the chosen preview_index.",
            }

        return await self.store.mutation(request_id, "character_prompt_preview", args, invoke)

    def character_preview_images(self, result, max_side=768):
        """Hash-verified previews saved by preview_character_from_prompt, as bounded JPEG thumbnails."""
        images = []
        for preview in result.get("previews", []):
            artifact_id = preview.get("artifact_id")
            if not artifact_id:
                continue
            data, _ = self.store.read_artifact(artifact_id)
            with Image.open(io.BytesIO(data)) as image:
                image = image.convert("RGB")
                image.thumbnail((max_side, max_side))
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=85)
            images.append((preview["preview_index"], output.getvalue()))
        return images

    async def create_character_from_prompt(self, request_id, preview_request_id, preview_index, name):
        text(name)
        identifier(preview_request_id)
        if isinstance(preview_index, bool) or not isinstance(preview_index, int) or preview_index < 0:
            raise ValueError("preview_index must be a whole number from the preview list")
        preview = self.store.get_request(preview_request_id)
        if preview.get("operation") != "character_prompt_preview" or preview["state"] != "complete":
            raise ValueError("preview_request_id must name a completed preview_character_from_prompt request")
        result = preview["result"]
        chosen = next((p for p in result["previews"] if p["preview_index"] == preview_index), None)
        if chosen is None:
            raise ValueError("preview_index is not in that preview list")
        args = {
            "preview_request_id": preview_request_id,
            "character_id": result["character_id"],
            "image_key": chosen["image_key"],
            "name": name,
        }

        async def invoke():
            created = await self.api.finalize_character_prompt(
                result["character_id"], result["prompt"], chosen["image_key"], name
            )
            return {
                **created,
                "name": name,
                "prompt": result["prompt"],
                "preview_index": preview_index,
                "review_status": "unreviewed",
                "stage": "character_created",
            }

        return await self.store.mutation(request_id, "character_from_prompt", args, invoke)

    async def loop(
        self,
        request_id,
        motion_id,
        character_id=TAR,
        trim_start_pct=0.0,
        trim_end_pct=1.0,
        zone_duration=2.0,
        loop_mode="closed",
        zone_mode="modify",
        zone_end_position=None,
    ):
        identifier(motion_id)
        identifier(character_id)
        number(trim_start_pct, 0, 1)
        number(trim_end_pct, 0, 1)
        number(zone_duration, 0, 3)
        if trim_start_pct >= trim_end_pct or zone_duration <= 0:
            raise ValueError(
                f"trim_start_pct must be less than trim_end_pct and zone_duration must be > 0 and <= 3 seconds (received {trim_start_pct}, {trim_end_pct}, {zone_duration})"
            )
        if loop_mode not in {"closed", "open"} or zone_mode not in {"modify", "extend"}:
            raise ValueError("Choose closed/open and modify/extend")
        if zone_end_position is not None:
            target_error = "An open-loop target requires x/y and optional facing_angle"
            if not isinstance(zone_end_position, dict):
                raise ValueError(target_error)
            target_in_closed_loop = loop_mode != "open"
            invalid_target_fields = not {"x", "y"} <= zone_end_position.keys() <= {"x", "y", "facing_angle"}
            if target_in_closed_loop or invalid_target_fields:
                raise ValueError(target_error)
            for value in zone_end_position.values():
                number(value, -1e6, 1e6)
        completed = self.store.completed(request_id, "loop")
        source = completed["source"] if completed else await self.api.motion(motion_id)
        args = {
            "motion_id": motion_id,
            "character_id": character_id,
            "trim_start_pct": trim_start_pct,
            "trim_end_pct": trim_end_pct,
            "zone_duration": zone_duration,
            "loop_mode": loop_mode,
            "zone_mode": zone_mode,
            "zone_end_position": zone_end_position,
            "source_bundle_id": source["bundle_id"],
            "source_bundle_sha256": source["bundle_sha256"],
        }
        if completed:
            return self.recovered_saved(self.store.replay(request_id, "loop", args))

        async def invoke():
            provider_args = {k: v for k, v in args.items() if not k.startswith("source_bundle_")}
            result = await self.api.loop(**provider_args)
            return {
                **result,
                "source_motion_id": motion_id,
                "source": source,
                "loop_intended": True,
                "loop_mode": loop_mode,
                "zone_mode": zone_mode,
                "review_status": "unreviewed",
                "preview_api": True,
            }

        receipt = await self.store.mutation(request_id, "loop", args, invoke)
        return await self.verify_saved(receipt)

    async def stitch_auto(self, request_id, options):
        options = AutoStitchOptions.model_validate(options).model_dump(exclude_none=True)
        args = {"preparation_mode": "server", **options}
        if self.store.completed(request_id, "stitch"):
            return self.recovered_saved(self.store.replay(request_id, "stitch", args))
        sources = [await self.api.motion(options[key]) for key in ("prefix_motion_id", "suffix_motion_id")]
        for label, source in zip(("prefix", "suffix"), sources):
            start = options[f"{label}_start_seconds"]
            end = options.get(f"{label}_end_seconds", source["last_sample_seconds"])
            if not start < end <= source["last_sample_seconds"]:
                raise ValueError(f"{label} trims must fit the motion's native sample range")

        async def invoke():
            result = await self.api.stitch_auto(options)
            return {
                **result,
                "source_motion_id": sources[0]["motion_id"],
                "source_motion_ids": [source["motion_id"] for source in sources],
                "source": sources[0],
                "sources": sources,
                "pose_samples_source": "server_sampled",
                "loop_intended": False,
                "review_status": "unreviewed",
                "preview_api": True,
            }

        receipt = await self.store.mutation(request_id, "stitch", args, invoke)
        return await self.verify_saved(receipt)

    async def stitch(self, request_id, prefix, suffix, character_id=TAR, stitch_duration=2.0, prompt=""):
        identifier(character_id)
        number(stitch_duration, 0.1, 3)
        if not isinstance(prompt, str) or len(prompt) > 1000:
            raise ValueError("Stitch prompt must be text of at most 1000 characters")
        # Validate/copy the complete sampled input before any API access.
        clips = [StitchClip.model_validate(clip).model_dump() for clip in (prefix, suffix)]
        for clip in clips:
            if clip["sampled_character_id"] != character_id:
                raise ValueError("Both clips must be sampled on the selected character")
            clip["source_bundle_sha256"] = clip["source_bundle_sha256"].lower()
        completed = self.store.completed(request_id, "stitch")
        args = {
            "prefix": clips[0],
            "suffix": clips[1],
            "character_id": character_id,
            "stitch_duration": stitch_duration,
            "prompt": prompt,
        }
        if completed:
            return self.recovered_saved(self.store.replay(request_id, "stitch", args))
        sources = [await self.api.motion(clip["motion_id"]) for clip in clips]
        params = [api_clip(clip, source, character_id, stitch_duration, prompt) for clip, source in zip(clips, sources)]

        async def invoke():
            result = await self.api.stitch(character_id, params[0], params[1])
            return {
                **result,
                "source_motion_id": clips[0]["motion_id"],
                "source_motion_ids": [clip["motion_id"] for clip in clips],
                "source": sources[0],
                "sources": sources,
                "stitch_duration_seconds": stitch_duration,
                "requested_intervals_seconds": [[clip["start_seconds"], clip["end_seconds"]] for clip in clips],
                "pose_samples_source": "host_supplied_not_independently_verified",
                "loop_intended": False,
                "review_status": "unreviewed",
                "preview_api": True,
            }

        receipt = await self.store.mutation(request_id, "stitch", args, invoke)
        return await self.verify_saved(receipt)

    async def characters(self, offset=0, limit=50, query=""):
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("query must be text of at most 200 characters")
        page_bounds(offset, limit)
        rows = await self.api.characters()
        scanned = len(rows)
        rows = [row for row in rows if query.casefold() in str(row.get("name", "")).casefold()]
        page = rows[offset : offset + limit]
        return {
            "characters": [{"character_id": identifier(row["id"]), "name": row.get("name")} for row in page],
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "pagination": "local_bounded_catalog",
            "scanned_count": scanned,
            "scope_note": "The API returns a full catalog capped at 16 MiB. Name filtering and paging occur locally; concurrent changes can shift offsets.",
        }

    async def motions(self, query="", source="available", method=None, offset=0, limit=20):
        catalog_filters(query, source, method, offset, limit)
        return motion_page(await self.api.motion_catalog(), query, source, method, offset, limit)

    async def usage(self):
        return usage_snapshot(await self.api.usage())

    async def download_allowed(self, motion_id, character_id=TAR):
        identifier(motion_id)
        identifier(character_id)
        return {
            **await self.api.download_allowed(motion_id, character_id),
            "motion_id": motion_id,
            "character_id": character_id,
            "reserves_allowance": False,
            "operation_cost_known": False,
            "note": "Read-only eligibility now, not a price quote or guarantee. The export rechecks access and allowance.",
        }

    async def preview(self, motion_id, character_id=TAR, format="apng"):
        identifier(motion_id)
        identifier(character_id)
        if format not in {"apng", "webm"}:
            raise ValueError("Preview format must be apng or webm")
        data = await self.api.preview(motion_id, character_id, format)
        metadata = {
            "motion_id": motion_id,
            "character_id": character_id,
            "format": format,
            "review_status": "unreviewed",
            "export_effects_applied": False,
            "credits_used": 0,
            "billing": receipt_billing("preview", {}),
        }
        if format == "apng":
            with Image.open(io.BytesIO(data)) as img:
                if img.format != "PNG":
                    raise ValueError("Preview endpoint did not return PNG/APNG")
                metadata.update(self.preview_timing(img))
            suffix, mime = ".png", "image/apng"
        else:
            if not data.startswith(b"\x1aE\xdf\xa3"):
                raise ValueError("Preview endpoint did not return WebM")
            suffix, mime = ".webm", "video/webm"
        return self.store.artifact(data, suffix, {**metadata, "mime_type": mime})

    @staticmethod
    def preview_timing(img):
        if img.width * img.height > 4_000_000 or img.n_frames > 1200:
            raise ValueError("Preview exceeds image or frame limits")
        img.seek(0)
        first = 1 if img.info.get("default_image") else 0
        timestamps, elapsed, usable = [], 0.0, True
        for index in range(first, img.n_frames):
            img.seek(index)
            timestamps.append(round(elapsed, 6))
            try:
                duration = number(img.info.get("duration"), 0, 60_000)
            except ValueError:
                usable = False
                continue
            if duration <= 0:
                usable = False
            elapsed += duration / 1000
        usable = usable and bool(timestamps)
        return {
            "frame_count": len(timestamps),
            "frame_times_seconds": timestamps if usable else [None] * len(timestamps),
            "preview_duration_seconds": elapsed if usable else None,
            "animated": len(timestamps) > 1,
            "default_image_excluded": bool(first),
            "timing_status": "available" if usable else "unavailable",
            "timing_basis": (
                "APNG frame delays; preview timing is not native trim metadata"
                if usable
                else "APNG frame delays are missing, zero, or unusable; use frame indexes, not timestamps"
            ),
        }

    def preview_frame(self, artifact_id, frame_index):
        data, metadata = self.store.read_artifact(artifact_id)
        if metadata.get("format") != "apng":
            raise ValueError("Fetch an APNG preview before requesting frames")
        if isinstance(frame_index, bool) or not isinstance(frame_index, int) or frame_index < 0:
            raise ValueError("Frame index is outside this preview")
        with Image.open(io.BytesIO(data)) as img:
            if img.format != "PNG":
                raise ValueError("Saved preview did not contain PNG/APNG")
            # Recheck the hash-verified bytes so old cached zero timestamps cannot mislabel frames.
            timing = self.preview_timing(img)
            if frame_index >= timing["frame_count"]:
                raise ValueError("Frame index is outside this preview")
            img.seek(frame_index + (1 if timing["default_image_excluded"] else 0))
            output = io.BytesIO()
            img.convert("RGBA").save(output, format="PNG")
        return output.getvalue(), {
            "motion_id": metadata["motion_id"],
            "character_id": metadata["character_id"],
            "frame_index": frame_index,
            "frame_count": timing["frame_count"],
            "time_seconds": timing["frame_times_seconds"][frame_index],
            "timing_status": timing["timing_status"],
            "timing_basis": timing["timing_basis"],
            "export_effects_applied": False,
        }

    async def download(
        self,
        request_id,
        motion_id,
        character_id=TAR,
        format="glb",
        fps=30,
        include_mesh=True,
        in_place=False,
        roblox_compatible=False,
        speed_multiplier=1.0,
        torso_only=False,
    ):
        identifier(motion_id)
        identifier(character_id)
        export_error = "Choose glb/fbx/bvh and 24/30/60 FPS"
        unsupported_format = format not in {"glb", "fbx", "bvh"}
        invalid_frame_rate = isinstance(fps, bool) or not isinstance(fps, int) or fps not in {24, 30, 60}
        if unsupported_format or invalid_frame_rate:
            raise ValueError(export_error)
        if not all(isinstance(x, bool) for x in (include_mesh, in_place, roblox_compatible, torso_only)):
            raise ValueError("Export switches must be booleans")
        speed_multiplier = float(number(speed_multiplier, 0, 2))
        if speed_multiplier == 0:
            raise ValueError("speed_multiplier must be greater than zero and at most 2")
        if format == "bvh" and include_mesh:
            raise ValueError("BVH contains skeleton animation only; set include_mesh=false or choose FBX/GLB")
        if roblox_compatible and format != "fbx":
            raise ValueError("Roblox export requires FBX")
        args = dict(
            motion_id=motion_id,
            character_id=character_id,
            format=format,
            fps=fps,
            include_mesh=include_mesh,
            in_place=in_place,
            roblox_compatible=roblox_compatible,
        )

        # Omit new default options from the fingerprint so pre-expansion receipts still replay.
        if speed_multiplier != 1:
            args["speed_multiplier"] = speed_multiplier
        if torso_only:
            args["torso_only"] = True

        if self.store.completed(request_id, "download"):
            result = self.store.replay(request_id, "download", args)
            self.store.read_artifact(result["artifact_id"])
            return result
        if roblox_compatible:
            metadata = await self.api.character_metadata(character_id)
            if metadata.get("engine") != "roblox":
                raise ValueError("Choose a supported Roblox character; arbitrary Mixamo rigs cannot use this preset")

        async def invoke():
            data = await self.api.download(**args)
            if not data:
                raise ValueError("Download returned an empty asset")
            return self.store.artifact(
                data,
                "." + format,
                {
                    **args,
                    "speed_multiplier": speed_multiplier,
                    "torso_only": torso_only,
                    "effective_in_place": in_place and not torso_only,
                    "review_status": "unreviewed",
                    "asset_kind": "retargeted_export",
                    "creates_new_motion": False,
                },
            )

        result = await self.store.mutation(request_id, "download", args, invoke)
        # Never silently charge for a replacement if the caller lost or modified their cached file.
        self.store.read_artifact(result["artifact_id"])
        return result

    async def save(self, request_id, file_path, source_motion_id, character_id, name):
        identifier(source_motion_id)
        identifier(character_id)
        text(name)
        completed = self.store.completed(request_id, "save")
        if completed and (
            completed["source_motion_id"] != source_motion_id or completed["character_id"] != character_id
        ):
            raise ValueError("request_id was already used with different arguments")
        # Calling save again still validates the supplied bytes. Recover by request ID when the original file is gone.
        filename, data, digest = self.read_input(file_path, {".gltf"})
        if len(data) > 16 * 1024 * 1024:
            raise ValueError("Saved GLTF JSON must be at most 16 MiB")
        try:
            gltf = data.decode("utf-8")
            document = json.loads(gltf)
        except (UnicodeDecodeError, ValueError):
            raise ValueError("Supply valid self-contained GLTF JSON") from None
        gltf_error = "Supply animated GLTF 2.0 JSON exported for this character"
        if not isinstance(document, dict):
            raise ValueError(gltf_error)
        asset = document.get("asset")
        if not isinstance(asset, dict):
            raise ValueError(gltf_error)
        animations = document.get("animations")
        if not isinstance(animations, list):
            raise ValueError(gltf_error)
        unsupported_gltf_version = asset.get("version") != "2.0"
        missing_animations = not animations
        invalid_animation_entries = not all(isinstance(animation, dict) for animation in animations)
        if unsupported_gltf_version or missing_animations or invalid_animation_entries:
            raise ValueError(gltf_error)

        # The native importer writes one file. Reject network/sidecar dependencies anywhere in it.
        def validate_uris(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "uri" and (not isinstance(item, str) or not item.startswith("data:")):
                        raise ValueError("GLTF must embed its buffers/images; external URIs are unsupported")
                    validate_uris(item)
            elif isinstance(value, list):
                for item in value:
                    validate_uris(item)

        validate_uris(document)
        source = completed["source"] if completed else await self.api.motion(source_motion_id)
        args = {
            "content_sha256": digest,
            "source_motion_id": source_motion_id,
            "character_id": character_id,
            "name": name,
            "source_bundle_sha256": source["bundle_sha256"],
        }

        if completed:
            return self.recovered_saved(self.store.replay(request_id, "save", args))

        async def invoke():
            result = await self.api.save(gltf, name, source_motion_id, character_id)
            return {
                **result,
                "source_motion_id": source_motion_id,
                "character_id": character_id,
                "source": source,
                "review_status": "unreviewed",
            }

        return await self.verify_saved(await self.store.mutation(request_id, "save", args, invoke))
