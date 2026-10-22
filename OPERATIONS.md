# Operational checks and attribution

The open-source MCP runs locally through stdio. There is no persistent local HTTP endpoint to ping. Run the packaged `uthana-mcp-smoke` command from the installed environment to start the server, initialize MCP, discover tools, read `uthana://workflow`, and stop it. It creates temporary private state and makes no paid request. A success means the package and local protocol work; it does not establish account access or generation quality.

Use `uthana-mcp-smoke --api-read` only with a deliberately configured `UTHANA_API_KEY` or `UTHANA_API_KEY_FILE`. It adds one read-only `get_usage` call to the selected `UTHANA_DOMAIN`. It creates no character, motion, job, or export. The command prints no account values or response bodies. Failure exits nonzero with a short category. Supply credentials through the host environment or a private key file, never command arguments.

The MCP identifies requests reaching the configured Uthana API host with `X-Uthana-AppId: mcp` and `User-Agent: uthana-mcp/<package version>`. This follows the existing app-ID convention used by Uthana clients. Attribution does not identify every local tool invocation: discovery and workflow reads remain local, and open-source users can change their code. It is not billing evidence. External asset-storage URLs do not receive the MCP attribution header or Uthana credentials.

For deployment monitoring, schedule the read-only smoke check in the existing monitoring system and alert on nonzero exits. Keep its key and schedule in the deployment environment, outside this repository. A hosted HTTP health endpoint belongs to the hosted deployment and should be checked separately. Sample paid generation only as an explicitly budgeted acceptance run, not a frequent health check.

When diagnosing a failure, record the MCP version, environment, tool name, request or job ID, and sanitized error category. Preserve durable receipts for interrupted mutations. Do not log API keys, raw prompts, private assets, account balances, or full state files.
