"""Single-asset lifecycle for characters and motions: rename, soft delete, and restore.

Each call reads the asset first, changes only assets owned by the caller's organization, and
reports what happened. The backend also enforces ownership in the same statement as each change
for every API call, so a restore, which cannot pre-read a deleted asset, never changes another
organization's asset. The calls are idempotent and keep no local receipt, so a batch caller can
apply them item by item and a retry after an unknown outcome reports the current state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .api import UthanaAPI

from .errors import APIError
from .validation import AssetRecord, identifier, text

Kind = Literal["character", "motion"]
KINDS = ("character", "motion")
NOT_VISIBLE = {"not_found", "permission"}

DELETE_EFFECTS = {
    "character": [
        "The character disappears from list_characters and can no longer be used for exports, previews, or generation.",
        "Share pages that show this character stop working.",
    ],
    "motion": [
        "The motion disappears from list_motions and can no longer be previewed or exported.",
        "Share pages that show this motion stop working.",
    ],
}
KEPT = {
    "character": [
        "Motions are not owned by a character; every motion is kept and can be exported on another character.",
        "Files already downloaded are unaffected.",
    ],
    "motion": [
        "Motions made from it (trims, loops, stitches, saved edits) are separate motions and are kept.",
        "Characters and files already downloaded are unaffected.",
    ],
}


def _kind(kind: str) -> Kind:
    if kind not in KINDS:
        raise ValueError("kind must be character or motion")
    return kind


def _not_visible(kind: str, asset_id: str) -> str:
    return (
        f"No live {kind} with ID {asset_id} is visible to this account. It may already be deleted, "
        "belong to another organization, or not exist. Nothing was changed."
    )


class AssetLifecycle:
    """Ownership-checked lifecycle changes over the MCP API adapter."""

    def __init__(self, api: UthanaAPI) -> None:
        self.api = api

    async def _visible(self, kind: Kind, asset_id: str) -> AssetRecord | None:
        try:
            return await self.api.asset(kind, asset_id)
        except APIError as error:
            if error.category in NOT_VISIBLE:
                return None
            raise

    async def _require_owned(self, kind: Kind, record: AssetRecord) -> None:
        org_id = await self.api.org_id()
        if record["org_id"] != org_id:
            raise APIError(
                f"{kind.capitalize()} {record['id']} ({record['name']!r}) is a built-in Uthana asset or belongs to "
                "another organization. Only your organization's own assets can be renamed, deleted, or restored. "
                "Nothing was changed.",
                category="not_owned",
                outcome="rejected",
            )

    async def _visible_owned(self, kind: Kind, asset_id: str) -> AssetRecord:
        record = await self._visible(kind, asset_id)
        if record is None:
            raise APIError(_not_visible(kind, asset_id), category="not_found", outcome="rejected")
        await self._require_owned(kind, record)
        return record

    @staticmethod
    def _confirmed(kind: Kind, asset_id: str, updated: AssetRecord, *, deleted: bool, name: str | None = None) -> dict:
        is_expected = (
            updated["id"] == asset_id
            and bool(updated["deleted"]) is deleted
            and (name is None or updated["name"] == name)
        )
        if not is_expected:
            raise APIError(
                f"Uthana returned an unexpected {kind} state after the change; inspect the {kind} before retrying.",
                category="provider_error",
            )
        return updated

    async def rename(self, kind: str, asset_id: str, *, name: str) -> dict:
        kind = _kind(kind)
        identifier(asset_id)
        text(name)
        record = await self._visible_owned(kind, asset_id)
        base = {"kind": kind, "asset_id": asset_id, "previous_name": record["name"], "name": name}
        if record["name"] == name:
            return {**base, "outcome": "unchanged", "changed": False}
        updated = await self.api.update_asset(kind, asset_id, action="rename", name=name)
        self._confirmed(kind, asset_id, updated, deleted=False, name=name)
        return {**base, "outcome": "renamed", "changed": True}

    async def delete(self, kind: str, asset_id: str) -> dict:
        kind = _kind(kind)
        identifier(asset_id)
        record = await self._visible(kind, asset_id)
        if record is None:
            return {
                "kind": kind,
                "asset_id": asset_id,
                "outcome": "not_found_or_already_deleted",
                "changed": False,
                "message": _not_visible(kind, asset_id),
            }
        await self._require_owned(kind, record)
        updated = await self.api.update_asset(kind, asset_id, action="delete")
        self._confirmed(kind, asset_id, updated, deleted=True)
        return {
            "kind": kind,
            "asset_id": asset_id,
            "name": updated["name"],
            "outcome": "deleted",
            "changed": True,
            "deleted_at": updated["deleted"],
            "deletion": "soft",
            "restorable": True,
            "restore_tool": f"restore_{kind}",
            "effects": DELETE_EFFECTS[kind],
            "kept": KEPT[kind],
            "note": f"Keep this ID: a deleted {kind} is not listed, and restore_{kind} needs the ID.",
        }

    async def restore(self, kind: str, asset_id: str) -> dict:
        kind = _kind(kind)
        identifier(asset_id)
        record = await self._visible(kind, asset_id)
        if record is not None:
            await self._require_owned(kind, record)
            return {
                "kind": kind,
                "asset_id": asset_id,
                "name": record["name"],
                "outcome": "already_active",
                "changed": False,
            }
        try:
            # The backend restores only if the caller's organization owns the asset, admins included.
            updated = await self.api.update_asset(kind, asset_id, action="restore")
        except APIError as error:
            if error.category == "permission":
                raise APIError(
                    f"No deleted {kind} with ID {asset_id} belongs to your organization. Nothing was changed.",
                    category="not_found",
                    outcome="rejected",
                ) from None
            raise
        self._confirmed(kind, asset_id, updated, deleted=False)
        return {
            "kind": kind,
            "asset_id": asset_id,
            "name": updated["name"],
            "outcome": "restored",
            "changed": True,
        }
