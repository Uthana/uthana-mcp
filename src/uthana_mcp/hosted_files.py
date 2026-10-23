"""Owned uploads and safe attachment imports for the hosted transport."""

import asyncio
import hashlib
import io
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlsplit

import httpx
from mcp.types import TextContent
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from .operations import MAX_UPLOAD_BYTES, Operations

MAX_ATTACHMENT_URL_LENGTH = 4096
MAX_STORED_INPUT_BYTES = 1024 * 1024 * 1024
MIN_FREE_DISK_BYTES = 2 * 1024 * 1024 * 1024
UPLOAD_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".fbx", ".glb", ".gltf", ".png", ".jpg", ".jpeg", ".webp"})
ATTACHMENT_HOSTS = ("oaiusercontent.com", "usercontent.openai.com")
FILE_ID = re.compile(r"^[a-f0-9]{32}$")


class InputFile(BaseModel):
    """Portable file descriptor, compatible with OpenAI's file input convention."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    file_id: str = Field(min_length=1, max_length=200)
    download_url: str = Field(min_length=1, max_length=MAX_ATTACHMENT_URL_LENGTH)
    file_name: str = Field(default="", max_length=200)
    mime_type: str = Field(default="", max_length=100)


class UploadedFile(TypedDict):
    file_id: str
    download_url: str
    file_name: str


class Files:
    def __init__(self, operations: Operations, origin: str) -> None:
        self.operations = operations
        self.origin = origin
        self.directory = operations.store.directory / "inputs"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        operations.input_directory = self.directory

    def save(self, data: bytes, filename: str) -> UploadedFile:
        suffix = Path(filename).suffix.lower()
        if suffix not in UPLOAD_EXTENSIONS or not 0 < len(data) <= MAX_UPLOAD_BYTES:
            raise ValueError("Upload must have a supported file extension and fit the configured upload size limit")
        self.validate_content(data, suffix)
        file_id = hashlib.sha256(data + suffix.encode()).hexdigest()[:32]
        path = self.directory / (file_id + suffix)
        with self.operations.store.connect() as database:
            database.execute("BEGIN IMMEDIATE")
            if not path.exists():
                used = sum(item.stat().st_size for item in self.directory.iterdir() if item.is_file())
                if (
                    used + len(data) > MAX_STORED_INPUT_BYTES
                    or shutil.disk_usage(self.directory).free < len(data) + MIN_FREE_DISK_BYTES
                ):
                    raise ValueError("Upload storage is full for this account; contact the service operator")
                with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                    stream.write(data)
            elif path.is_symlink() or path.read_bytes() != data:
                raise ValueError("An uploaded file no longer matches its original content")
        return {
            "file_id": file_id,
            "download_url": f"{self.origin}/files/inputs/{file_id}",
            "file_name": Path(filename).name,
        }

    @staticmethod
    def validate_content(data: bytes, suffix: str) -> None:
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            try:
                with Image.open(io.BytesIO(data)) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"}:
                        raise ValueError("Upload a supported PNG, JPEG or WebP image")
                    image.verify()
            except (OSError, Image.DecompressionBombError) as error:
                raise ValueError("Upload a valid supported image") from error
        elif suffix == ".gltf":
            try:
                document = json.loads(data)
            except (ValueError, UnicodeError):
                raise ValueError("Upload valid self-contained GLTF JSON") from None
            if (
                not isinstance(document, dict)
                or not isinstance(document.get("asset"), dict)
                or document["asset"].get("version") != "2.0"
            ):
                raise ValueError("Upload a GLTF 2.0 document")
        elif suffix == ".glb" and (
            len(data) < 20
            or data[:4] != b"glTF"
            or int.from_bytes(data[4:8], "little") != 2
            or int.from_bytes(data[8:12], "little") != len(data)
        ):
            raise ValueError("Upload a valid GLB 2.0 file")
        elif suffix == ".fbx" and not (data.startswith(b"Kaydara FBX Binary") or data.lstrip().startswith(b"; FBX")):
            raise ValueError("Upload a supported binary or ASCII FBX file")
        elif suffix in {".mp4", ".mov"} and not any(atom in data[:64] for atom in (b"ftyp", b"moov", b"mdat")):
            raise ValueError("Upload a supported MP4 or MOV file")
        elif suffix == ".webm" and not data.startswith(b"\x1aE\xdf\xa3"):
            raise ValueError("Upload a valid WebM file")

    def input_path(self, file_id: str) -> Path:
        if not FILE_ID.fullmatch(file_id):
            raise ValueError("Invalid uploaded file handle")
        paths = list(self.directory.glob(file_id + ".*"))
        if len(paths) != 1 or paths[0].is_symlink() or not paths[0].is_file():
            raise ValueError("Uploaded file was not found for this account")
        return paths[0]

    async def resolve(self, descriptor: InputFile) -> str:
        parsed = urlsplit(descriptor.download_url)
        if descriptor.download_url == f"{self.origin}/files/inputs/{descriptor.file_id}":
            return str(self.input_path(descriptor.file_id))
        hostname = parsed.hostname or ""
        is_provider_host = any(hostname == host or hostname.endswith("." + host) for host in ATTACHMENT_HOSTS)
        if (
            parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or not is_provider_host
        ):
            raise ValueError("Use an owned upload handle or a supported HTTPS attachment")
        # Trusted attachment hosts only; no arbitrary URLs or redirect chains.
        # Validate all resolved addresses as an additional guard against private-network fetching.
        cache_key = hashlib.sha256(descriptor.file_id.encode()).hexdigest()
        cache = self.directory / (cache_key + ".attachment")
        if cache.is_file() and not cache.is_symlink():
            return str(self.input_path(cache.read_text()))
        addresses = await asyncio.to_thread(socket.getaddrinfo, hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
            raise ValueError("Attachment host must resolve to public addresses")
        data = bytearray()
        try:
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30) as client:
                async with client.stream("GET", descriptor.download_url) as response:
                    if response.status_code != 200:
                        raise ValueError("Attachment download failed; upload the file again")
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        data.extend(chunk)
                        if len(data) > MAX_UPLOAD_BYTES:
                            raise ValueError("Attachment exceeds the upload size limit")
        except httpx.HTTPError:
            raise ValueError("Attachment download could not be completed; upload the file again") from None
        filename = descriptor.file_name or Path(parsed.path).name
        if Path(filename).suffix.lower() not in UPLOAD_EXTENSIONS:
            suffix = mimetypes.guess_extension(descriptor.mime_type) or ""
            if suffix not in UPLOAD_EXTENSIONS:
                if data.startswith(b"glTF"):
                    suffix = ".glb"
                elif data.startswith(b"\x89PNG"):
                    suffix = ".png"
                elif data.startswith(b"\xff\xd8"):
                    suffix = ".jpg"
                elif data.startswith(b"Kaydara FBX Binary") or data.lstrip().startswith(b"; FBX"):
                    suffix = ".fbx"
                elif data.startswith(b"\x1aE\xdf\xa3"):
                    suffix = ".webm"
                elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                    suffix = ".webp"
                elif any(atom in data[:64] for atom in (b"ftyp", b"moov", b"mdat")):
                    suffix = ".mp4"
                elif data.lstrip().startswith(b"{"):
                    suffix = ".gltf"
            filename = "attachment" + suffix
        uploaded = self.save(bytes(data), filename)
        try:
            with os.fdopen(os.open(cache, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                stream.write(uploaded["file_id"])
        except FileExistsError:
            if cache.is_symlink() or cache.read_text() != uploaded["file_id"]:
                raise ValueError("Attachment ID was reused with different content") from None
        return str(self.input_path(uploaded["file_id"]))

    def project(self, value: object) -> object:
        if isinstance(value, TextContent):
            try:
                document = json.loads(value.text)
            except ValueError:
                return value
            return value.model_copy(update={"text": json.dumps(self.project(document))})
        if isinstance(value, dict):
            result = {
                key: self.project(item)
                for key, item in value.items()
                if key not in {"local_path", "file_path", "data_dir", "input_dir"}
            }
            if isinstance(artifact_id := value.get("artifact_id"), str):
                result["download_url"] = f"{self.origin}/files/artifacts/{artifact_id}"
            return result
        if isinstance(value, list):
            return [self.project(item) for item in value]
        return value
