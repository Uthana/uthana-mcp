"""MCP result normalization over the shared Uthana Python client's public modules.

The client owns API documents, multipart handling, routes, and HTTP transport.
This layer applies explicit environment configuration and conservative, redacted MCP outcomes.
"""

import hashlib
import math

import httpx
from uthana import Org, StitchInput, StitchResult, TtmJobModelType, Uthana
from uthana.types import CharacterPreviewResult, UthanaError

from .attribution import MCPTransport
from .errors import APIError, graphql_error, read_error
from .validation import UTHANA_DOMAIN, AssetRecord, asset_record, identifier, motion_metadata, normalize_job


class StitchAPIResult(StitchResult):
    motion_id: str
    character_id: str


class UthanaAPI:
    def __init__(
        self,
        key: str | None,
        domain: str | None = None,
        *,
        transport=None,
        access_token: str | httpx.Auth | None = None,
        scope: str | None = None,
    ) -> None:
        self.domain = domain or UTHANA_DOMAIN
        self.mcp_transport = MCPTransport(self.domain, transport)
        transport = self.mcp_transport
        self.transport = transport
        if access_token is None and (not key or not key.strip()):
            raise ValueError("Configure UTHANA_API_KEY in the host environment")
        if access_token is not None and not scope:
            raise ValueError("Hosted authentication requires a stable verified identity scope")
        self.scope = scope or hashlib.sha256((self.domain + ":" + key).encode()).hexdigest()
        # The current API has no upstream character pagination. Isolate its
        # larger, bounded catalog response from all mutation/metadata limits.
        self.catalog_client = Uthana(
            key,
            access_token=access_token,
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
            access_token=access_token,
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
                if status == 429 and isinstance(error.response_data, dict):
                    rejection = graphql_error(error.response_data, mutation_field)
                    if rejection.outcome == "rejected" and rejection.category == "rate_limit":
                        rejection.http_status = status
                        raise rejection from None
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

    async def generate(
        self,
        prompt,
        duration_seconds,
        character_id,
        *,
        model: TtmJobModelType = "text-to-motion-3.0",
        fast: bool = False,
    ):
        job = await self._call(
            self.client.ttm.create_job,
            prompt,
            model=model,
            fast=fast,
            character_id=character_id,
            length=duration_seconds,
            rewrite_prompt=True,
            mutation_field="create_text_to_motion_job",
        )
        return {
            "job_id": identifier(job["id"]),
            "provider_status": job.get("status"),
            "character_id": character_id,
            "model": model,
        }

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

    async def library_search(self, prompt: str, character_id: str) -> dict[str, object]:
        result = await self._call(
            self.client.ttm.library_search,
            prompt,
            character_id=character_id,
            mutation_field="create_text_to_motion",
        )
        score = result.match_score
        return {
            "motion_id": identifier(result.motion_id),
            "character_id": character_id,
            "name": result.name,
            "match_score": None if score is None or not math.isfinite(score) else round(score, 4),
        }

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

    async def stitch(self, options: StitchInput) -> StitchAPIResult:
        result = await self._call(
            self.client.motions.stitch,
            options,
            timeout=httpx.Timeout(360, connect=15),
            mutation_field="stitch",
        )
        return {
            "motion": result["motion"],
            "motion_id": identifier(result["motion"]["id"]),
            "character_id": options["character_id"],
            "resolved_steps": result["resolved_steps"],
        }

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
        origin = self.mcp_transport.origin
        if (parsed.scheme, parsed.host, parsed.port) == (origin.scheme, origin.host, origin.port):
            return await self._call(self.client._request_bytes, "GET", url, max_bytes=max_bytes, read_only=True)
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

    async def org(self) -> Org:
        """Read the current organization without caching its changing allowances."""
        row: object = await self._call(self.client.org.get_org, read_only=True)
        if not isinstance(row, dict):
            raise APIError("Uthana returned an invalid organization record", outcome="not_applicable")
        try:
            org_id = identifier(row.get("id"))
        except ValueError:
            raise APIError("Uthana returned an invalid organization ID", outcome="not_applicable") from None
        result: Org = {"id": org_id}
        if "name" in row:
            name = row["name"]
            if name is not None and not isinstance(name, str):
                raise APIError("Uthana returned an invalid organization name", outcome="not_applicable")
            result["name"] = name
        for field in ("motion_download_secs_per_month", "motion_download_secs_per_month_remaining"):
            if field in row:
                value = row[field]
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                    raise APIError("Uthana returned an invalid organization allowance", outcome="not_applicable")
                if field == "motion_download_secs_per_month":
                    result["motion_download_secs_per_month"] = value
                else:
                    result["motion_download_secs_per_month_remaining"] = value
        return result

    async def org_id(self) -> str:
        return (await self.org())["id"]

    async def asset(self, kind: str, asset_id: str) -> AssetRecord:
        """Read one live character or motion with its owning organization."""
        module = self.client.characters if kind == "character" else self.client.motions
        row = await self._call(module.get, identifier(asset_id), read_only=True, resource=kind)
        return asset_record(row)

    async def update_asset(self, kind: str, asset_id: str, *, action: str, name: str | None = None) -> AssetRecord:
        """Rename, soft-delete, or restore one character or motion your organization owns.

        The backend checks ownership in the same statement as the change, so
        another organization's asset is refused unchanged, even for admin accounts.
        """
        module = self.client.characters if kind == "character" else self.client.motions
        if action == "rename":
            call = (module.rename, identifier(asset_id), name)
        elif action in {"delete", "restore"}:
            call = (getattr(module, action), identifier(asset_id))
        else:
            raise ValueError("action must be rename, delete, or restore")
        row = await self._call(*call, mutation_field=f"update_{kind}")
        return asset_record(row)

    async def download_character(self, character_id: str, format: str) -> bytes:
        return await self._call(
            self.client.characters.download,
            identifier(character_id),
            output_format=format,
            max_bytes=128 * 1024 * 1024,
            read_only=True,
        )

    async def motion_catalog(self):
        return await self._call(self.client.motions.catalog, read_only=True)

    async def usage(self):
        return await self._call(self.client.org.get_usage, read_only=True)

    async def ledger(self, **filters: object) -> list[dict]:
        return await self._call(self.client.org.get_ledger, read_only=True, **filters)

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
