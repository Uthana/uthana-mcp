"""Bounded, read-only smoke check for an installed Uthana MCP server."""

import argparse
import asyncio
import os
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class SmokeFailure(Exception):
    """Safe failure category with no upstream response text."""


async def step(category: str, operation, timeout: float):
    try:
        return await asyncio.wait_for(operation, timeout)
    except Exception:
        raise SmokeFailure(category) from None


async def check(api_read: bool, timeout: float) -> None:
    env = os.environ.copy()
    if not api_read:
        env.pop("UTHANA_API_KEY", None)
        env.pop("UTHANA_API_KEY_FILE", None)
    elif not env.get("UTHANA_API_KEY") and not env.get("UTHANA_API_KEY_FILE"):
        raise SmokeFailure("authentication configuration")
    with tempfile.TemporaryDirectory(prefix="uthana-mcp-smoke-") as state:
        env["UTHANA_MCP_DATA_DIR"] = state
        params = StdioServerParameters(command=sys.executable, args=["-m", "uthana_mcp.server"], env=env)
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as client:
                    await step("initialization", client.initialize(), timeout)
                    tools = await step("tool discovery", client.list_tools(), timeout)
                    if not tools.tools:
                        raise SmokeFailure("tool discovery")
                    workflow = await step("workflow resource", client.read_resource("uthana://workflow"), timeout)
                    if not workflow.contents or not workflow.contents[0].text:
                        raise SmokeFailure("workflow resource")
                    if api_read:
                        result = await step("account read", client.call_tool("get_usage", {}), timeout)
                        if result.isError:
                            raise SmokeFailure("account read")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check an installed Uthana MCP without creating assets or jobs")
    parser.add_argument("--api-read", action="store_true", help="also check configured API credentials via get_usage")
    parser.add_argument("--timeout", type=float, default=20, help="seconds allowed for each protocol step")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    try:
        asyncio.run(check(args.api_read, args.timeout))
    except Exception as error:
        # AnyIO can wrap step failures in nested exception groups. Extract only
        # our safe category; never print upstream exceptions or response bodies.
        def category(failure):
            if isinstance(failure, SmokeFailure):
                return str(failure)
            for nested in getattr(failure, "exceptions", ()):
                found = category(nested)
                if found:
                    return found
            return None

        print(
            f"Uthana MCP smoke check failed: {category(error) or 'server startup or shutdown'}",
            file=sys.stderr,
        )
        return 1
    print("Uthana MCP smoke check passed: protocol and workflow" + ("; account read" if args.api_read else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
