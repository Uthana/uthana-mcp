"""HTTP transport adapters; operators supply authentication and per-request API credentials."""

import functools
import hashlib
import inspect
import json
import logging
import mimetypes
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api import UthanaAPI
from .hosted_files import Files, InputFile
from .operations import MAX_UPLOAD_BYTES, Operations
from .server import create_server

MAX_IN_FLIGHT_PER_USER = 4
MAX_PROTOCOL_REQUEST_BYTES = 4 * 1024 * 1024
_CURRENT: ContextVar["Runtime"] = ContextVar("uthana_hosted_runtime")


@dataclass(frozen=True)
class Identity:
    subject: str
    organization: str
    scopes: frozenset[str]

    @property
    def scope(self) -> str:
        return hashlib.sha256(json.dumps([self.subject, self.organization]).encode()).hexdigest()


@dataclass
class Runtime:
    identity: Identity
    operations: Operations
    files: "Files"


def _https_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        transport_url = httpx.URL(value)
        has_unsafe_characters = "\\" in value or any(
            character.isspace() or not character.isprintable() for character in value
        )
        has_extra_components = parsed.path not in ("", "/") or "?" in value or "#" in value
        has_credentials = parsed.username is not None or parsed.password is not None
        has_valid_authority = (
            parsed.scheme == "https" and bool(parsed.hostname) and bool(transport_url.host) and parsed.port != 0
        )
        if not has_valid_authority or has_unsafe_characters or has_extra_components or has_credentials:
            raise ValueError
    except (ValueError, httpx.InvalidURL):
        raise ValueError("Hosted configuration requires an HTTPS origin without credentials or a path") from None
    return value.rstrip("/")


def _requires_write_permission(annotations: ToolAnnotations | None) -> bool:
    return annotations is None or annotations.readOnlyHint is not True


def transform_tool(
    function: Callable[..., Any], annotations: ToolAnnotations | None
) -> tuple[Callable[..., Any], dict]:
    signature = inspect.signature(function)
    has_input_file = "file_path" in signature.parameters
    parameters = [
        parameter.replace(name="input_file", annotation=InputFile) if parameter.name == "file_path" else parameter
        for parameter in signature.parameters.values()
    ]

    @functools.wraps(function)
    async def invoke(**kwargs: Any) -> Any:
        runtime = _CURRENT.get()
        if has_input_file:
            descriptor = InputFile.model_validate(kwargs.pop("input_file"))
            kwargs["file_path"] = await runtime.files.resolve(descriptor)
        result = function(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return runtime.files.project(result)

    invoke.__signature__ = signature.replace(parameters=parameters)
    invoke.__doc__ = (function.__doc__ or "").replace("file_path", "input_file").replace("local file", "uploaded file")
    return invoke, {"meta": {"openai/fileParams": ["input_file"]}} if has_input_file else {}


class HostedMCP(FastMCP):
    async def list_tools(self) -> list[Tool]:
        tools = await super().list_tools()
        declared = []
        for tool in tools:
            scopes = ["mcp:read"]
            if _requires_write_permission(tool.annotations):
                scopes.append("mcp:write")
            schemes = [{"type": "oauth2", "scopes": scopes}]
            declared.append(
                tool.model_copy(
                    update={"securitySchemes": schemes, "meta": {**(tool.meta or {}), "securitySchemes": schemes}}
                )
            )
        return declared

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        runtime = _CURRENT.get()
        tool = self._tool_manager.get_tool(name)
        if tool and _requires_write_permission(tool.annotations) and "mcp:write" not in runtime.identity.scopes:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text="Reconnect Uthana with write permission for this operation")],
                _meta={
                    "mcp/www_authenticate": [
                        'Bearer error="insufficient_scope", error_description="Write permission is required", scope="mcp:read mcp:write"'
                    ]
                },
            )
        return await super().call_tool(name, arguments)


UPLOAD_PAGE = """<!doctype html><title>Uthana uploads</title><h1>Upload a file for your agent</h1>
<p>Choose a video, character, image, or self-contained animation file. Copy the returned file handle to your agent.</p>
<input id="file" type="file"><button id="upload">Upload</button><pre id="result"></pre>
<script>
document.getElementById('upload').onclick = async () => {
 const file = document.getElementById('file').files[0]; if (!file) return;
 const response = await fetch('/files', {method:'POST', headers:{'X-Filename':encodeURIComponent(file.name)}, body:file});
 document.getElementById('result').textContent = JSON.stringify(await response.json(), null, 2);
};
</script>"""


def create_app(
    *,
    origin: str,
    directory: Path,
    authenticate: Callable[[Request], Awaitable[Identity | None]],
    api_factory: Callable[[Request, Identity], Awaitable[UthanaAPI]],
    issuer: str,
    allowed_origins: tuple[str, ...] = (),
    login_url: str | None = None,
    readiness: Callable[[], Awaitable[bool]] | None = None,
) -> Starlette:
    """Compose an HTTP service around operator-provided authorization.

    The authenticator must verify token audience, expiry, revocation, scopes and
    stable account identity on every request. Cookie authentication also requires
    CSRF protection for writes. The API factory must supply separate upstream
    credentials bound to that verified identity, not forward the incoming token.
    """
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    origin = _https_origin(origin)
    parsed = urlsplit(origin)

    def current() -> Operations:
        return _CURRENT.get().operations

    server = create_server(
        operations_provider=current,
        tool_transform=transform_tool,
        server_class=HostedMCP,
        api_domain=urlsplit(issuer).netloc,
        http_settings={
            "host": "127.0.0.1",
            "stateless_http": True,
            "max_request_body_size": MAX_PROTOCOL_REQUEST_BYTES,
            "json_response": True,
            "transport_security": TransportSecuritySettings(
                allowed_hosts=[parsed.netloc], allowed_origins=[origin, *allowed_origins]
            ),
        },
    )
    http_app = server.streamable_http_app()
    in_flight: dict[str, int] = {}

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with server.session_manager.run():
            yield

    async def health(request: Request) -> Response:
        if request.url.path == "/ready":
            is_ready = os.access(directory, os.W_OK) and (readiness is None or await readiness())
            return JSONResponse(
                {"status": "ready" if is_ready else "unavailable"}, status_code=200 if is_ready else 503
            )
        return JSONResponse({"status": "ok"})

    async def discovery(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "resource": origin + "/mcp",
                "authorization_servers": [issuer],
                "scopes_supported": ["mcp:read", "mcp:write"],
                "bearer_methods_supported": ["header"],
            }
        )

    async def uploads(request: Request) -> Response:
        runtime = _CURRENT.get()
        if request.method == "GET":
            return HTMLResponse(
                UPLOAD_PAGE,
                headers={
                    "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; style-src 'self'; frame-ancestors 'none'"
                },
            )
        if "mcp:write" not in runtime.identity.scopes:
            return JSONResponse({"error": "Write permission is required for uploads"}, status_code=403)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_BYTES:
                return JSONResponse({"error": "Upload exceeds size limit"}, status_code=413)
        try:
            result = runtime.files.save(bytes(data), unquote(request.headers.get("X-Filename", "")))
            return JSONResponse(result, status_code=201)
        except ValueError as error:
            return JSONResponse({"error": str(error)}, status_code=400)

    async def download(request: Request) -> Response:
        runtime = _CURRENT.get()
        kind, file_id = request.path_params["kind"], request.path_params["file_id"]
        try:
            if kind == "inputs":
                path = runtime.files.input_path(file_id)
                data, filename = path.read_bytes(), path.name
            elif kind == "artifacts":
                data, metadata = runtime.operations.store.read_artifact(file_id)
                filename = Path(metadata["local_path"]).name
            else:
                raise ValueError("Unknown file kind")
        except (ValueError, OSError):
            return JSONResponse({"error": "File not found for this account"}, status_code=404)
        return Response(
            data,
            media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/ready", health),
            Route("/.well-known/oauth-protected-resource", discovery),
            Route("/.well-known/oauth-protected-resource/mcp", discovery),
            Route("/files", uploads, methods=["GET", "POST"]),
            Route("/files/{kind}/{file_id}", download),
            Mount("/", http_app),
        ],
        lifespan=lifespan,
    )

    class IdentityMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                return await self.app(scope, receive, send)
            request_id = uuid.uuid4().hex
            original_send = send

            async def correlated_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() not in {b"cache-control", b"referrer-policy"}
                    ]
                    message["headers"] = [
                        *headers,
                        (b"x-request-id", request_id.encode()),
                        (b"cache-control", b"no-store"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                    logging.getLogger(__name__).info(
                        "hosted_mcp request_id=%s status=%s", request_id, message["status"]
                    )
                await original_send(message)

            send = correlated_send
            request = Request(scope, receive)
            if request.url.path in {
                "/health",
                "/ready",
                "/.well-known/oauth-protected-resource",
                "/.well-known/oauth-protected-resource/mcp",
            } or request.url.path.startswith("/auth/"):
                return await self.app(scope, receive, send)
            if request.headers.get("origin") not in (None, origin, *allowed_origins):
                return await JSONResponse({"error": "Origin is not allowed"}, status_code=403)(scope, receive, send)
            try:
                identity = await authenticate(request)
            except HTTPException as error:
                return await JSONResponse({"error": error.detail}, status_code=error.status_code)(scope, receive, send)
            if identity is None or "mcp:read" not in identity.scopes:
                if request.url.path == "/mcp" and request.method == "POST":
                    body = bytearray()
                    async for chunk in request.stream():
                        body.extend(chunk)
                        if len(body) > MAX_PROTOCOL_REQUEST_BYTES:
                            return await JSONResponse(
                                {"error": "Protocol request exceeds size limit"}, status_code=413
                            )(scope, receive, send)
                    try:
                        payload = json.loads(body)
                    except (ValueError, RecursionError):
                        payload = None
                    if isinstance(payload, dict) and payload.get("method") in {
                        "initialize",
                        "notifications/initialized",
                        "tools/list",
                        "resources/list",
                        "resources/templates/list",
                        "prompts/list",
                    }:
                        has_delivered_body = False

                        async def replay_receive() -> Message:
                            nonlocal has_delivered_body
                            if not has_delivered_body:
                                has_delivered_body = True
                                return {"type": "http.request", "body": bytes(body), "more_body": False}
                            return await receive()

                        return await self.app(scope, replay_receive, send)
                    if isinstance(payload, dict) and payload.get("method") == "tools/call":
                        challenge = f'Bearer resource_metadata="{origin}/.well-known/oauth-protected-resource", error="invalid_token", error_description="Link your Uthana account to continue"'
                        result = CallToolResult(
                            isError=True,
                            content=[TextContent(type="text", text="Link your Uthana account to continue")],
                            _meta={"mcp/www_authenticate": [challenge]},
                        )
                        response = JSONResponse(
                            {
                                "jsonrpc": "2.0",
                                "id": payload.get("id"),
                                "result": result.model_dump(by_alias=True, exclude_none=True),
                            }
                        )
                        return await response(scope, receive, send)
                if login_url and request.method == "GET" and request.url.path.startswith("/files"):
                    response = RedirectResponse(login_url + "?next=" + request.url.path)
                else:
                    response = JSONResponse(
                        {"error": "Account linking is required"},
                        status_code=401,
                        headers={
                            "WWW-Authenticate": f'Bearer resource_metadata="{origin}/.well-known/oauth-protected-resource"'
                        },
                    )
                return await response(scope, receive, send)
            key = identity.scope
            if in_flight.get(key, 0) >= MAX_IN_FLIGHT_PER_USER:
                return await JSONResponse(
                    {"error": "Too many active requests for this account"},
                    status_code=429,
                    headers={"Retry-After": "10"},
                )(scope, receive, send)
            in_flight[key] = in_flight.get(key, 0) + 1
            api = None
            token = None
            try:
                api = await api_factory(request, identity)
                api.scope = hashlib.sha256((origin + ":" + identity.scope).encode()).hexdigest()
                operations = Operations(api, directory)
                token = _CURRENT.set(Runtime(identity, operations, Files(operations, origin)))
                await self.app(scope, receive, send)
            finally:
                if token is not None:
                    _CURRENT.reset(token)
                in_flight[key] -= 1
                if not in_flight[key]:
                    del in_flight[key]
                if api is not None:
                    await api.close()

    app.add_middleware(IdentityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin, *allowed_origins],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "MCP-Protocol-Version",
            "Mcp-Session-Id",
            "X-Filename",
        ],
        expose_headers=["WWW-Authenticate", "X-Request-ID", "Mcp-Session-Id"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[httpx.URL(origin).host], www_redirect=False)
    return app
