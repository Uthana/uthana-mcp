# Hosted transport integration

The local stdio connector remains the supported installation. The HTTP adapter is
for operators implementing an authenticated hosted service; it does not start an
anonymous server or use a shared customer API key.

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

Hosted results replace local paths with authenticated `download_url` values.
Clients fetch them using their OAuth authorization; browsers use the operator's
account-linked portal. Reconnect to regain access to the same result, rather than
repeating generation or export. Receipt identity survives token refresh and service
restart; a different user or organization receives a different state namespace.

Keep one service instance with durable storage. Preserve that storage during
upgrades, restore it before host replacement, and never replay pending or unknown
mutations automatically. Use the operator's enrollment and support process.

Uthana's hosted pilot is invitation-only. The public source and PyPI package do not
grant pilot access. Hosted onboarding becomes the recommended route after pilot
acceptance; local stdio remains available. A ChatGPT viewer and public listing are
separate work.
