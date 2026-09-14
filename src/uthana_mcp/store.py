"""Private, credential-scoped operation receipts; no automatic mutation retries."""

import asyncio
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .artifact_io import read_artifact_bytes
from .billing import receipt_billing
from .errors import APIError
from .fingerprints import fingerprint, matches
from .validation import identifier


class Store:
    def __init__(self, directory: Path, scope: str):
        self.directory = Path(directory).expanduser().resolve() / scope
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.path = self.directory / "requests.sqlite"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, operation TEXT NOT NULL, fingerprint TEXT NOT NULL,
                state TEXT NOT NULL, result TEXT, updated REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, filename TEXT NOT NULL, metadata TEXT NOT NULL)""")
            if "error" not in {row[1] for row in db.execute("PRAGMA table_info(requests)")}:
                db.execute("ALTER TABLE requests ADD COLUMN error TEXT")
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get_request(self, request_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT operation,state,result,updated,error FROM requests WHERE id=?", (identifier(request_id),)
            ).fetchone()
        if row is None:
            return {"request_id": request_id, "state": "not_found"}
        return {
            "request_id": request_id,
            "operation": row[0],
            "state": row[1],
            "result": json.loads(row[2]) if row[2] else None,
            "updated_at_unix": row[3],
            "error": json.loads(row[4]) if row[4] else None,
            "next_action": (
                "Correct the reported cause, then explicitly retry the same request ID and arguments"
                if row[1] == "rejected"
                else "Inspect staging; do not resubmit" if row[1] != "complete" else None
            ),
        }

    @staticmethod
    def fingerprint(operation, args):
        return fingerprint(operation, args)

    def completed(self, request_id, operation):
        """Inspect local state before dependencies; this alone does not validate changed caller arguments."""
        status = self.get_request(request_id)
        if status["state"] == "not_found":
            return None
        if status["operation"] != operation:
            raise ValueError("request_id was already used with different arguments")
        if status["state"] == "complete":
            return status["result"]
        if status["state"] == "rejected":
            return None
        raise ValueError("Request is pending or unresolved. Inspect get_request_status and staging; do not resubmit")

    def replay(self, request_id, operation, args):
        with self.connect() as db:
            row = db.execute(
                "SELECT fingerprint,state,result FROM requests WHERE id=?", (identifier(request_id),)
            ).fetchone()
        if row is None or not matches(row[0], operation, args):
            raise ValueError("request_id was already used with different arguments")
        if row[1] != "complete":
            raise ValueError(
                "Request is pending or unresolved. Inspect get_request_status and staging; do not resubmit"
            )
        return {**json.loads(row[2]), "replayed": True}

    def record_verification(self, request_id, observation):
        """Retain native verification evidence without rewriting the confirmed operation."""
        identifier(request_id)
        if observation.get("status") not in {"unverified", "failed", "verified_metadata"}:
            raise ValueError("Invalid saved-motion verification status")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT operation,state,result FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None or row[0] not in {"trim", "save"} or row[1] != "complete":
                raise ValueError("Verification requires a completed trim or save receipt")
            result = json.loads(row[2])
            previous = result.get("previous_verification")
            # An unavailable metadata read cannot overturn a conclusive earlier finding.
            if observation["status"] != "unverified" or not previous or previous["status"] == "unverified":
                previous = observation
            history = {"previous_verification": previous, "last_verification_attempt": observation}
            result.update(history)
            db.execute(
                "UPDATE requests SET result=? WHERE id=?",
                (json.dumps(result, allow_nan=False), request_id),
            )
        return history

    async def mutation(self, request_id, operation, args, invoke):
        identifier(request_id)
        fingerprint = self.fingerprint(operation, args)
        with self.connect() as db:
            # Claim atomically across local processes before making any upstream mutation.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fingerprint,state,result FROM requests WHERE id=?", (request_id,)).fetchone()
            if row:
                if not matches(row[0], operation, args):
                    raise ValueError("request_id was already used with different arguments")
                if row[1] == "complete":
                    return {**json.loads(row[2]), "replayed": True}
                if row[1] != "rejected":
                    raise ValueError(
                        "Request is pending or unresolved. Inspect get_request_status and staging; do not resubmit"
                    )
                db.execute(
                    "UPDATE requests SET state='pending',result=NULL,error=NULL,updated=? WHERE id=?",
                    (time.time(), request_id),
                )
            else:
                db.execute(
                    "INSERT INTO requests (id,operation,fingerprint,state,result,updated) VALUES (?,?,?,'pending',NULL,?)",
                    (request_id, operation, fingerprint, time.time()),
                )
        try:
            result = await invoke()
            billing = receipt_billing(operation, args)
            result = {
                **result,
                "request_id": request_id,
                "billing": billing,
                "credits_used": 0 if billing["cost_status"] == "free_by_policy" else None,
                "usage_status": "free_by_policy" if billing["cost_status"] == "free_by_policy" else "unknown",
            }
            encoded = json.dumps(result, allow_nan=False)
        except (Exception, asyncio.CancelledError) as exc:
            error = (
                exc
                if isinstance(exc, APIError)
                else APIError(
                    (
                        "Submission was interrupted; upstream work may continue."
                        if isinstance(exc, asyncio.CancelledError)
                        else "Operation outcome is unconfirmed. Inspect staging before any further submission"
                    ),
                    category="interrupted" if isinstance(exc, asyncio.CancelledError) else "unconfirmed",
                )
            )
            state = "rejected" if error.outcome == "rejected" else "unknown"
            with self.connect() as db:
                db.execute(
                    "UPDATE requests SET state=?,error=?,updated=? WHERE id=?",
                    (state, json.dumps(error.details()), time.time(), request_id),
                )
            if isinstance(exc, asyncio.CancelledError):
                raise
            if state == "rejected":
                raise APIError(
                    f"{error} Correct the cause, then explicitly retry the same request ID and arguments.",
                    category=error.category,
                    outcome="rejected",
                    http_status=error.http_status,
                ) from None
            raise RuntimeError(f"{error} Use get_request_status; do not resubmit an unconfirmed operation.") from None
        with self.connect() as db:
            db.execute(
                "UPDATE requests SET state='complete',result=?,updated=? WHERE id=?", (encoded, time.time(), request_id)
            )
        return {**result, "replayed": False}

    def artifact(self, data: bytes, suffix: str, metadata: dict):
        artifact_id = uuid.uuid4().hex
        filename = artifact_id + suffix
        path = self.directory / filename
        # Exclusive creation and private permissions, independent of the caller's umask.
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
            f.write(data)
        record = {
            **metadata,
            "artifact_id": artifact_id,
            "local_path": str(path),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
        with self.connect() as db:
            db.execute("INSERT INTO artifacts VALUES (?,?,?)", (artifact_id, filename, json.dumps(record)))
        return record

    def read_artifact(self, artifact_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT filename,metadata FROM artifacts WHERE id=?", (identifier(artifact_id),)
            ).fetchone()
        if not row:
            raise ValueError("Artifact not found in this credential's local state")
        path = self.directory / row[0]
        metadata = json.loads(row[1])
        data = read_artifact_bytes(path, metadata)
        return data, metadata
