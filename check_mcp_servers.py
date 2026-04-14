"""
check_mcp_servers.py — Health-check script for all configured MCP servers.

Run: python check_mcp_servers.py

Tests each MCP server by:
  1. Spawning the npx process
  2. Initialising an MCP client session
  3. Listing available tools
  4. Running a minimal smoke-test tool call
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


# ── Per-server smoke tests ────────────────────────────────────────────────────

_SMOKE_TESTS: dict[str, dict] = {
    "brave_search": {
        "tool": "brave_web_search",
        "args": {"query": "test MCP connection", "count": 1},
        "description": "Brave Web Search",
    },
    "fetch": {
        "tool": "fetch",
        "args": {"url": "https://example.com", "max_length": 500},
        "description": "Fetch URL content",
    },
    "github": {
        "tool": "search_repositories",
        "args": {"query": "python stars:>1000", "perPage": 2},
        "description": "GitHub Repo Search",
    },
    "memory": {
        "tool": "create_entities",
        "args": {"entities": [{"name": "test_check", "entityType": "test", "observations": ["ok"]}]},
        "description": "Memory Store Entity",
    },
}


async def _check_server(server_name: str) -> dict[str, Any]:
    """Attempt to connect to a single MCP server and run a smoke test."""
    result: dict[str, Any] = {
        "server": server_name,
        "status": "❌ FAIL",
        "tools_found": 0,
        "smoke_test": "—",
        "latency_ms": None,
        "error": "",
    }

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from config import MCP_SERVERS, MCP_CALL_TIMEOUT, MCP_INIT_TIMEOUT
    except ImportError as e:
        result["error"] = f"Import error: {e}"
        return result

    if server_name not in MCP_SERVERS:
        result["error"] = "Not configured"
        return result

    cfg = MCP_SERVERS[server_name]
    env = {**os.environ, **cfg["env"]}
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env=env)

    t0 = time.perf_counter()
    try:
        async with asyncio.timeout(MCP_INIT_TIMEOUT + MCP_CALL_TIMEOUT):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=MCP_INIT_TIMEOUT)

                    # List tools
                    tools_resp = await asyncio.wait_for(session.list_tools(), timeout=10)
                    tools = tools_resp.tools if hasattr(tools_resp, "tools") else []
                    result["tools_found"] = len(tools)
                    result["status"] = "✅ OK"

                    # Smoke test
                    smoke = _SMOKE_TESTS.get(server_name)
                    if smoke:
                        try:
                            await asyncio.wait_for(
                                session.call_tool(smoke["tool"], smoke["args"]),
                                timeout=MCP_CALL_TIMEOUT,
                            )
                            result["smoke_test"] = f"✅ {smoke['description']}"
                        except Exception as se:
                            result["smoke_test"] = f"⚠️  {str(se)[:60]}"

    except asyncio.TimeoutError:
        result["error"] = "Timeout"
        result["status"] = "⏱ TIMEOUT"
    except Exception as e:
        result["error"] = str(e)[:80]

    result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

async def check_all() -> None:
    from config import MCP_SERVERS, validate_required_keys

    console.print("\n[bold cyan]MCP Server Health Check[/]\n")

    # API key pre-flight
    missing = validate_required_keys()
    if missing:
        console.print(f"[yellow]⚠  Missing env vars: {missing} — some servers may fail[/]\n")

    server_names = list(MCP_SERVERS.keys())
    console.print(f"Testing {len(server_names)} servers: {', '.join(server_names)}\n")

    tasks = [_check_server(name) for name in server_names]
    results = await asyncio.gather(*tasks)

    tbl = Table(header_style="bold blue", show_lines=True)
    tbl.add_column("Server",     style="cyan",   min_width=14)
    tbl.add_column("Status",     min_width=12)
    tbl.add_column("Tools",      justify="right", min_width=6)
    tbl.add_column("Smoke Test", min_width=30)
    tbl.add_column("Latency",    justify="right", min_width=10)
    tbl.add_column("Error",      style="red",    min_width=20)

    all_ok = True
    for r in results:
        if "FAIL" in r["status"] or "TIMEOUT" in r["status"]:
            all_ok = False
        tbl.add_row(
            r["server"],
            r["status"],
            str(r["tools_found"]),
            r["smoke_test"],
            f"{r['latency_ms']} ms" if r["latency_ms"] is not None else "—",
            r["error"],
        )

    console.print(tbl)

    if all_ok:
        console.print("\n[bold green]All MCP servers are healthy ✓[/]\n")
    else:
        console.print("\n[bold yellow]Some servers need attention — check errors above.[/]")
        console.print(
            "[dim]Common fixes:\n"
            "  • Run: npm install -g @modelcontextprotocol/server-brave-search\n"
            "  • Check BRAVE_API_KEY / GITHUB_TOKEN in your .env\n"
            "  • Ensure Node.js >= 18 is installed (node --version)[/]\n"
        )


if __name__ == "__main__":
    asyncio.run(check_all())
