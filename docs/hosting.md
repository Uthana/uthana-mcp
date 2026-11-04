# Hosted integration for operators

To connect an AI client to Uthana, use the [hosted connection guide](https://uthana.com/docs/api/capabilities/hosted-mcp). The local [stdio connector](installation.md) is also available with an API key.

This guide is for operators integrating the HTTP adapter with their own authorization and storage. The adapter does not start an anonymous server or use a shared customer API key.

Use `uthana_mcp.hosted.create_app` with an HTTPS origin, issuer, durable state
directory, asynchronous request authenticator and per-request API factory. The
verified identity contains a stable subject, organization and scopes (`mcp:read`,
`mcp:write`). The factory supplies a separately delegated upstream credential.
Never trust user or organization IDs supplied in tool arguments or session headers.
All tools and file routes authenticate on every request. Discovery is public.

Hosted tools preserve the local workflows, but replace `file_path` with `input_file`:

```json
{
  "file_id": "owned-upload-handle",
  "download_url": "https://your-mcp.example/files/inputs/owned-upload-handle",
  "file_name": "character.glb"
}
```

Upload through the authenticated `/files` endpoint (raw bytes, `X-Filename` header)
or the operator-provided file portal. Compatible OpenAI file descriptors are also
accepted from supported attachment hosts. Arbitrary URLs and redirects are rejected.
The tool advertises `openai/fileParams` for these inputs. Operation-specific file
formats and limits still apply; generated file handles belong to one account only.

Hosted results replace local paths with `download_url` values. With the operator's download-grant callbacks configured, export links last 15 minutes and can be fetched directly without forwarding OAuth tokens. `get_artifact_download` renews an owned cached artifact's link without another export. Otherwise links require OAuth authorization; browsers use the operator's
account-linked portal. Reconnect to regain access to the same result, rather than
repeating generation or export. Receipt identity survives token refresh and service
restart; a different user or organization receives a different state namespace.

Keep one service instance with durable storage. Preserve that storage during
upgrades, restore it before host replacement, and never replay pending or unknown
mutations automatically. Use the operator's support process.

## Discoverable sign-in

Hosted MCP requires OAuth before initialization and tool discovery. A client adds
only the HTTPS `/mcp` URL, receives a 401 discovery challenge, discovers the
issuer's public metadata, establishes its client identity using CIMD or DCR,
and opens normal sign-in/consent. It then retries MCP initialization with its token.
No client ID, client secret, or API key should need to be entered manually.

The operator's issuer must implement its advertised registration methods and
PKCE callback validation. Download grants are optional operator callbacks: mint
only after the adapter verifies artifact ownership, and validate expiry, grant
revocation, account activity, and organization on every redemption. Capability
URLs delegate access to one file; do not log them or put them in public content.
Existing authenticated file routes remain available.

`viewer_url` points at the configured issuer's `/app/play/{character_id}/{motion_id}`
when both IDs are known. A viewer URL is separate from an exported file's download
URL. A client should use the returned URLs instead of constructing its own.

Clients need Streamable HTTP and OAuth discovery support. Local stdio configuration does not connect to the hosted service.
