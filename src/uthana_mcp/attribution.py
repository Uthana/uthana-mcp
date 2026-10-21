"""Identify MCP-originated requests using the existing Uthana app header."""

from importlib.metadata import version

import httpx


class MCPTransport(httpx.AsyncBaseTransport):
    def __init__(self, domain: str, transport: httpx.AsyncBaseTransport | None = None):
        self.domain = domain.lower()
        self.transport = transport or httpx.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # The shared client creates a fresh HTTPX client for each request. Add
        # attribution at the transport boundary without changing its auth,
        # redirect, timeout, or response handling.
        if request.url.scheme == "https" and request.url.host.lower() == self.domain:
            request.headers["X-Uthana-AppId"] = "mcp"
            request.headers["User-Agent"] = f"uthana-mcp/{version('uthana-mcp')}"
        return await self.transport.handle_async_request(request)

    async def aclose(self) -> None:
        # The shared SDK creates and closes an AsyncClient for every request.
        # Keep this transport alive until the UthanaAPI itself is closed.
        pass

    async def shutdown(self) -> None:
        await self.transport.aclose()
