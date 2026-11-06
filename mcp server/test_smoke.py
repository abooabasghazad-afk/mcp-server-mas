"""Smoke test: boot the MCP server over stdio, list tools, call one, and
verify the API client reaches the real backend (expect a clean 401 error
dict when called without a session token)."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_CMD = [sys.executable, "-m", "mastime_mcp.server"]


async def main() -> None:
    async with stdio_client(StdioServerParameters(command=SERVER_CMD[0], args=SERVER_CMD[1:])) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"TOOL COUNT: {len(names)}")
            for n in names:
                print("  -", n)

            required = {
                "mastime_login", "mastime_create_room", "mastime_get_timer_state",
                "mastime_timer_action", "mastime_add_speaker", "mastime_admin_stats",
                "mastime_public_state", "mastime_speaker_enter", "mastime_upload_file",
            }
            missing = required - set(names)
            if missing:
                raise SystemExit(f"MISSING TOOLS: {sorted(missing)}")

            # Call one tool without a session: the server should return a
            # structured error dict (401), proving HTTP wiring works.
            res = await session.call_tool("mastime_me", {})
            text = res.content[0].text if res.content else ""
            data = json.loads(text)
            print("CALL mastime_me ->", json.dumps(data, ensure_ascii=False)[:200])
            assert data.get("ok") is False, "expected a structured error without login"
            assert data.get("status") == 401, f"expected 401, got {data.get('status')}"
            print("SMOKE TEST OK")


if __name__ == "__main__":
    asyncio.run(main())
