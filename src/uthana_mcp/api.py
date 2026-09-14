"""MCP result normalization over the shared Uthana Python client's public modules.

The client owns API documents, multipart handling, routes, and HTTP transport.
This layer applies staging configuration and conservative, redacted MCP outcomes.
"""

import hashlib

import httpx
from uthana import Uthana
from uthana.types import UthanaError

from .errors import APIError, graphql_error, read_error
from .validation import STAGING, identifier, motion_metadata, normalize_job


class UthanaAPI:
    def __init__(self, key: str, domain: str = STAGING, *, transport=None):
        if domain != STAGING:
            raise ValueError("This pilot requires UTHANA_DOMAIN=staging.uthana.com; no production fallback")
        if not key or not key.strip():
            raise ValueError("Configure UTHANA_API_KEY in the host environment")
        self.scope = hashlib.sha256((domain + ":" + key).encode()).hexdigest()
        self.client = Uthana(
            key,
            domain=domain,
            timeout=httpx.Timeout(180, connect=15),
            telemetry=False,
            trust_env=False,
            transport=transport,
            max_response_bytes=2 * 1024 * 1024,
        )

    async def close(self):
        self.client.close()

    async def _call(self, function, *args, read_only=False, mutation_field=None, **kwargs):
        if read_only and mutation_field:
            raise ValueError("A mutation cannot use read-only error handling")
        try:
            return await function(*args, **kwargs)
        except UthanaError as error:
            if error.kind == "graphql" and isinstance(error.response_data, dict):
                raise graphql_error(error.response_data, mutation_field, read_only=read_only) from None
            if error.kind == "http":
                status = error.status_code
                if read_only:
                    category = {401: "authentication", 403: "permission", 429: "rate_limit"}.get(status, "http_error")
                    raise read_error(category, http_status=status) from None
                if status in (401, 403):
                    category = "authentication" if status == 401 else "permission"
                    action = "Correct the staging API key" if status == 401 else "Check account and asset permissions"
                    raise APIError(
                        f"Uthana rejected this request (HTTP {status}). {action}.",
                        category=category,
                        outcome="rejected",
                        http_status=status,
                    ) from None
                raise APIError(
                    f"Uthana returned HTTP {status}; submission outcome is unconfirmed.",
                    category="rate_limit" if status == 429 else "http_error",
                    http_status=status,
                ) from None
            message = (
                "Uthana response exceeded the configured size limit"
                if error.kind == "response_too_large"
                else "Uthana returned an invalid API response"
            )
            raise APIError(message, outcome="not_applicable" if read_only else "unknown") from None
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            if read_only:
                raise read_error("connection") from None
            raise APIError(
                "Could not establish a Uthana connection; no request was submitted.",
                category="connection",
                outcome="rejected",
            ) from None
        except httpx.HTTPError:
            if read_only:
                raise read_error("connection") from None
            raise APIError(
                "Uthana connection failed after submission may have started; inspect the saved request.",
                category="connection",
            ) from None
        except (ValueError, KeyError, TypeError):
            raise APIError(
                "Uthana returned an invalid API response", outcome="not_applicable" if read_only else "unknown"
            ) from None

    async def generate(self, prompt, duration_seconds, character_id):
        job = await self._call(
            self.client.ttm.create_job,
            prompt,
            model="text-to-motion-3.0",
            character_id=character_id,
            length=duration_seconds,
            rewrite_prompt=True,
            mutation_field="create_text_to_motion_job",
        )
        return {"job_id": identifier(job["id"]), "provider_status": job.get("status"), "character_id": character_id}

    async def generate_v2(self, prompt, duration_seconds, character_id):
        result = await self._call(
            self.client.ttm.create,
            prompt,
            model="diffusion-v2",
            character_id=character_id,
            length=duration_seconds,
            foot_ik=True,
            mutation_field="create_text_to_motion",
        )
        return {"motion_id": identifier(result.motion_id), "character_id": character_id}

    async def locomotion_styles(self):
        return await self._call(self.client.motions.list_locomotion_styles, read_only=True)

    async def locomotion(self, character_id, strides, move_speed, style_id, travel_angle):
        result = await self._call(
            self.client.motions.create_locomotion,
            character_id,
            strides=strides,
            move_speed=move_speed,
            style_id=style_id,
            travel_angle=travel_angle,
            mutation_field="create_locomotion",
        )
        return {"motion_id": identifier(result.motion_id), "character_id": character_id}

    async def prices(self):
        return await self._call(self.client.org.get_prices, read_only=True)

    async def job(self, job_id):
        job = await self._call(self.client.jobs.get, identifier(job_id), read_only=True)
        if not job:
            raise APIError("Job not found or inaccessible")
        return normalize_job(job)

    async def motion(self, motion_id):
        motion = await self._call(self.client.motions.get, identifier(motion_id), read_only=True)
        if not motion:
            raise APIError("Motion not found or inaccessible")
        result = motion_metadata(motion)
        if result["motion_id"] != motion_id:
            raise APIError("Motion metadata returned a different motion ID")
        return result

    async def trim(self, motion_id, start, end, name):
        motion = await self._call(
            self.client.motions.trim, motion_id, start, end, name, mutation_field="trim_and_loop_motion"
        )
        return {"motion_id": identifier(motion["id"])}

    async def video(self, filename, content, name, model):
        job = await self._call(
            self.client.vtm.create_from_bytes,
            filename,
            content,
            motion_name=name,
            model=model,
            mutation_field="create_video_to_motion",
        )
        return {"job_id": identifier(job["id"]), "provider_status": job.get("status"), "model": model}

    async def upload_character(self, filename, content, name, auto_rig):
        result = await self._call(
            self.client.characters.create_from_bytes,
            filename,
            content,
            name=name,
            auto_rig=auto_rig,
            # Preserve defaults previously applied when the direct mutation omitted these fields.
            front_facing=True,
            include_fingers=True,
            timeout=httpx.Timeout(360, connect=15),
            mutation_field="create_character",
        )
        warning = result.message.strip() if isinstance(result.message, str) else ""
        return {
            "character_id": identifier(result.character_id),
            "auto_rig_confidence": result.auto_rig_confidence,
            "compatibility_warning": warning[:2000] or None,
            "compatibility_warning_truncated": len(warning) > 2000,
        }

    async def characters(self):
        return await self._call(self.client.characters.list, read_only=True)

    async def motion_catalog(self):
        return await self._call(self.client.motions.catalog, read_only=True)

    async def usage(self):
        return await self._call(self.client.org.get_usage, read_only=True)

    async def download_allowed(self, motion_id, character_id):
        result = await self._call(
            self.client.motions.download_allowed, identifier(motion_id), identifier(character_id), read_only=True
        )
        if not isinstance(result, dict):
            raise APIError("Download eligibility unavailable")
        if result.get("allowed") is not None and not isinstance(result["allowed"], bool):
            raise APIError("Invalid download eligibility response")
        return {"allowed": result.get("allowed"), "reason": result.get("reason")}

    async def character_metadata(self, character_id):
        return await self._call(
            self.client.characters.metadata, identifier(character_id), max_bytes=2 * 1024 * 1024, read_only=True
        )

    async def preview(self, motion_id, character_id, format):
        return await self._call(
            self.client.motions.preview,
            character_id,
            motion_id,
            format=format,
            max_bytes=32 * 1024 * 1024,
            timeout=httpx.Timeout(180, connect=15),
            read_only=True,
        )

    async def download(
        self,
        motion_id,
        character_id,
        format,
        fps,
        include_mesh,
        in_place,
        roblox_compatible,
        speed_multiplier=1.0,
        torso_only=False,
    ):
        return await self._call(
            self.client.motions.download,
            character_id,
            motion_id,
            output_format=format,
            fps=fps,
            no_mesh=not include_mesh,
            in_place=in_place,
            roblox_compatible=roblox_compatible,
            speed_multiplier=speed_multiplier if speed_multiplier != 1 else None,
            torso_only=torso_only or None,
            max_bytes=128 * 1024 * 1024,
        )

    async def save(self, gltf, name, source_motion_id, character_id):
        result = await self._call(
            self.client.motions.bake_with_changes,
            gltf,
            name,
            source_motion_id=source_motion_id,
            character_id=character_id,
            mutation_field="create_motion_from_gltf",
        )
        return {"motion_id": identifier(result.motion_id)}
