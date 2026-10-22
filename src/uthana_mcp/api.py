"""MCP result normalization over the shared Uthana Python client's public modules.

The client owns API documents, multipart handling, routes, and HTTP transport.
This layer applies explicit environment configuration and conservative, redacted MCP outcomes.
"""

import hashlib

import httpx
from uthana import Uthana
from uthana.types import CharacterPreviewResult, UthanaError

from .attribution import MCPTransport
from .errors import APIError, graphql_error, read_error
from .validation import UTHANA_DOMAIN, identifier, motion_metadata, normalize_job


class UthanaAPI:
    def __init__(self, key: str, domain: str | None = None, *, transport=None):
        self.domain = domain or UTHANA_DOMAIN
        self.mcp_transport = MCPTransport(self.domain, transport)
        transport = self.mcp_transport
        self.transport = transport
        if not key or not key.strip():
            raise ValueError("Configure UTHANA_API_KEY in the host environment")
        self.scope = hashlib.sha256((self.domain + ":" + key).encode()).hexdigest()
        # The current API has no upstream character pagination. Isolate its
        # larger, bounded catalog response from all mutation/metadata limits.
        self.catalog_client = Uthana(
            key,
            domain=self.domain,
            timeout=httpx.Timeout(180, connect=15),
            telemetry=False,
            trust_env=False,
            transport=transport,
            max_response_bytes=16 * 1024 * 1024,
        )
        response_limit = 2 * 1024 * 1024
        self.client = Uthana(
            key,
            domain=self.domain,
            timeout=httpx.Timeout(180, connect=15),
            telemetry=False,
            trust_env=False,
            transport=transport,
            max_response_bytes=response_limit,
            max_mutation_response_bytes=response_limit,
        )

    async def close(self):
        self.client.close()
        self.catalog_client.close()
        await self.mcp_transport.shutdown()

    async def _call(self, function, *args, read_only=False, mutation_field=None, resource=None, **kwargs):
        if read_only and mutation_field:
            raise ValueError("A mutation cannot use read-only error handling")
        try:
            return await function(*args, **kwargs)
        except UthanaError as error:
            if error.kind == "graphql" and isinstance(error.response_data, dict):
                raise graphql_error(
                    error.response_data, mutation_field, read_only=read_only, resource=resource
                ) from None
            if error.kind == "http":
                status = error.status_code
                if read_only:
                    category = {401: "authentication", 403: "permission", 404: "not_found", 429: "rate_limit"}.get(
                        status, "http_error"
                    )
                    raise read_error(category, http_status=status) from None
                if status in (401, 403):
                    category = "authentication" if status == 401 else "permission"
                    action = (
                        "Check the API key for the configured Uthana environment"
                        if status == 401
                        else "Check account and asset permissions"
                    )
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
            too_large = error.kind in {"response_too_large", "uncertain"}
            message = (
                "Uthana response exceeded the configured size limit"
                if too_large
                else "Uthana returned an invalid API response"
            )
            raise APIError(
                message,
                category="response_too_large" if too_large else "provider_error",
                outcome="not_applicable" if read_only else "unknown",
            ) from None
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

    async def generate_v1(self, prompt: str, *, character_id: str) -> dict[str, str]:
        """Generate a native V1 motion; this model chooses its own duration."""
        result = await self._call(
            self.client.ttm.create,
            prompt,
            model="vqvae-v1",
            character_id=identifier(character_id),
            foot_ik=True,
            mutation_field="create_text_to_motion",
        )
        return {"motion_id": identifier(result.motion_id), "character_id": character_id}

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
        job = await self._call(self.client.jobs.get, identifier(job_id), read_only=True, resource="job")
        if not job:
            raise read_error("not_found")
        return normalize_job(job)

    async def motion(self, motion_id):
        motion = await self._call(self.client.motions.get, identifier(motion_id), read_only=True, resource="motion")
        if not motion:
            raise read_error("not_found")
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

    async def upload_character(
        self, filename, content, name, auto_rig, front_facing=True, include_fingers=True, rerig_target=None
    ):
        result = await self._call(
            self.client.characters.create_from_bytes,
            filename,
            content,
            name=name,
            auto_rig=auto_rig,
            # Defaults match those previously applied when the direct mutation omitted these fields.
            front_facing=front_facing,
            include_fingers=include_fingers,
            rerig_target=rerig_target,
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

    async def prepare_character_image(self, filename, content):
        result = await self._call(
            self.client.characters.prepare_from_image_bytes,
            filename,
            content,
            max_bytes=16 * 1024 * 1024,
            timeout=httpx.Timeout(360, connect=15),
            mutation_field="create_image_from_image",
        )
        image_key = result.previews[0].get("key")
        if not isinstance(image_key, str) or not image_key.strip() or len(image_key) > 1024:
            raise APIError("Uthana returned an invalid prepared image key")
        return {"stage": "image_prepared", "character_id": identifier(result.character_id), "image_key": image_key}

    async def finalize_character_image(self, prepared, name, include_fingers=True):
        pending = CharacterPreviewResult(character_id=prepared["character_id"], previews=[], prompt="")
        result = await self._call(
            self.client.characters.generate_from_image,
            pending,
            prepared["image_key"],
            name=name,
            include_fingers=include_fingers,
            timeout=httpx.Timeout(660, connect=15),
            mutation_field="create_character_from_image",
        )
        character_id = identifier(result.character["id"])
        if character_id != prepared["character_id"]:
            raise APIError("Character generation returned a different character ID; inspect the prepared ID")
        return {"character_id": character_id, "auto_rig_confidence": result.auto_rig_confidence}

    async def preview_character_prompt(self, prompt):
        result = await self._call(
            self.client.characters.create_from_prompt,
            prompt=prompt,
            mutation_field="create_image_from_text",
        )
        previews = []
        for preview in result.previews if isinstance(result.previews, list) else []:
            key = preview.get("key") if isinstance(preview, dict) else None
            url = preview.get("url") if isinstance(preview, dict) else None
            if not isinstance(key, str) or not key.strip() or len(key) > 1024:
                raise APIError("Uthana returned an invalid character preview key")
            previews.append({"image_key": key, "url": url if isinstance(url, str) else None})
        if not previews:
            raise APIError("Uthana returned no character preview images")
        return {"character_id": identifier(result.character_id), "previews": previews}

    async def fetch_preview_image(self, url, max_bytes=16 * 1024 * 1024):
        """Fetch a generated preview. Send credentials only to the configured Uthana host."""
        parsed = httpx.URL(url)
        if parsed.scheme != "https":
            raise APIError("Character preview URL is not HTTPS")
        host = parsed.host or ""
        if host == self.domain or host.endswith("." + self.domain):
            return await self.client._request_bytes("GET", url, max_bytes=max_bytes)
        # Presigned storage URLs carry their own authorization; never attach the API key.
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=15),
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        ) as http:
            async with http.stream("GET", url) as response:
                if response.status_code != 200:
                    raise APIError(f"Character preview fetch failed with HTTP {response.status_code}")
                data = b""
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) > max_bytes:
                        raise APIError("Character preview exceeds the size limit")
        return data

    async def finalize_character_prompt(self, character_id, prompt, image_key, name):
        pending = CharacterPreviewResult(character_id=character_id, previews=[], prompt=prompt)
        result = await self._call(
            self.client.characters.generate_from_image,
            pending,
            image_key,
            name=name,
            include_fingers=True,
            timeout=httpx.Timeout(660, connect=15),
            mutation_field="create_character_from_image",
        )
        returned = identifier(result.character["id"])
        if returned != character_id:
            raise APIError("Character generation returned a different character ID; inspect the preview's ID")
        return {"character_id": returned, "auto_rig_confidence": result.auto_rig_confidence}

    async def stitch(self, character_id, prefix, suffix):
        result = await self._call(
            self.client.motions.create_stitched_motion,
            character_id,
            prefix,
            suffix,
            timeout=httpx.Timeout(360, connect=15),
            mutation_field="create_enhanced_stitched_motion",
        )
        return {"motion_id": identifier(result["id"]), "character_id": character_id}

    async def loop(
        self,
        motion_id,
        character_id,
        trim_start_pct,
        trim_end_pct,
        zone_duration,
        loop_mode,
        zone_mode,
        zone_end_position,
    ):
        result = await self._call(
            self.client.motions.create_looped_motion,
            character_id,
            motion_id,
            trim_start_pct=trim_start_pct,
            trim_end_pct=trim_end_pct,
            zone_duration=zone_duration,
            loop_mode=loop_mode,
            zone_mode=zone_mode,
            zone_end_position=zone_end_position,
            timeout=httpx.Timeout(360, connect=15),
            mutation_field="create_looped_motion",
        )
        return {"motion_id": identifier(result["id"]), "character_id": character_id}

    async def characters(self):
        try:
            return await self._call(self.catalog_client.characters.list, read_only=True)
        except APIError as error:
            if error.category == "response_too_large":
                raise APIError(
                    "Character catalog exceeds 16 MiB. The API has no upstream pagination; "
                    "smaller limit values cannot reduce this response. Contact Uthana support.",
                    category="catalog_too_large",
                    outcome="not_applicable",
                ) from None
            raise

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
