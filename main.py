"""
main.py — CLI entry point for the Multi-Agent CI/Market Research System.

Usage examples:
  python main.py "OpenAI competitors"
  python main.py "HR tech market" --format markdown
  python main.py --history
  python main.py --list-topics
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from config import validate_required_keys
from orchestrator import ResearchOrchestrator

console = Console()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)


# ── CLI helpers ───────────────────────────────────────────────────────────────

def _print_report(report: dict, fmt: str = "rich") -> None:
    if fmt == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    if fmt == "markdown":
        md_path = report.get("_file_paths", {}).get("markdown")
        if md_path:
            from pathlib import Path
            console.print(Path(md_path).read_text(encoding="utf-8"))
        else:
            console.print_json(json.dumps(report))
        return

    # Rich (default)
    eb = report.get("executive_briefing", {})
    meta = report.get("meta", {})

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]{eb.get('headline', 'Intelligence Briefing')}[/]\n"
            f"[dim]Generated: {meta.get('generated_at','')[:19]} UTC[/]",
            border_style="cyan",
        )
    )

    # Summary
    console.print(f"\n[bold]Executive Summary[/]\n{eb.get('summary', '')}")

    # Trends
    if eb.get("key_trends"):
        console.print("\n[bold yellow]Key Trends[/]")
        for t in eb["key_trends"]:
            console.print(f"  • {t}")

    # Threats / Opportunities
    if eb.get("threats"):
        console.print("\n[bold red]Threats[/]")
        for t in eb["threats"]:
            console.print(f"  ⚠  {t}")

    if eb.get("opportunities"):
        console.print("\n[bold green]Opportunities[/]")
        for o in eb["opportunities"]:
            console.print(f"  ✓  {o}")

    # Actions
    actions = report.get("recommended_actions", [])
    if actions:
        console.print("\n[bold magenta]Recommended Actions[/]")
        for i, a in enumerate(actions, 1):
            console.print(f"  {i}. {a}")

    # GitHub table
    gh = report.get("github_trends", [])
    if gh:
        console.print()
        tbl = Table(title="GitHub Trends", header_style="bold blue")
        tbl.add_column("Repository", style="cyan")
        tbl.add_column("Stars", justify="right")
        tbl.add_column("Language")
        tbl.add_column("Latest Release")
        for r in gh[:8]:
            tbl.add_row(
                r["full_name"],
                f"{r['stars']:,}",
                r.get("language", ""),
                r.get("latest_release", ""),
            )
        console.print(tbl)

    # File paths
    paths = report.get("_file_paths", {})
    if paths:
        console.print(
            f"\n[dim]Reports saved → JSON: {paths.get('json')}  |  "
            f"MD: {paths.get('markdown')}[/]"
        )

    elapsed = report.get("_elapsed_seconds")
    if elapsed:
        console.print(f"[dim]Completed in {elapsed}s[/]\n")


# ── Async runners ─────────────────────────────────────────────────────────────

async def _run_research(topic: str, fmt: str) -> None:
    missing = validate_required_keys()
    if missing:
        console.print(f"[bold red]Missing environment variables: {missing}[/]")
        console.print("Copy .env.example → .env and fill in your API keys.")
        sys.exit(1)

    with console.status(f"[cyan]Researching: {topic!r}…[/]", spinner="dots"):
        orch = ResearchOrchestrator()
        report = await orch.run(topic)

    _print_report(report, fmt)


async def _show_history() -> None:
    orch = ResearchOrchestrator()
    history = await orch.get_history()
    if not history:
        console.print("[dim]No query history found.[/]")
        return
    tbl = Table(title="Query History", header_style="bold cyan")
    tbl.add_column("#")
    tbl.add_column("Topic")
    tbl.add_column("Queried At")
    for i, row in enumerate(history, 1):
        tbl.add_row(str(i), row["topic"], row["queried_at"][:19])
    console.print(tbl)


async def _list_topics() -> None:
    orch = ResearchOrchestrator()
    topics = await orch.get_all_topics()
    if not topics:
        console.print("[dim]No topics researched yet.[/]")
        return
    console.print("[bold cyan]Topics researched so far:[/]")
    for t in topics:
        console.print(f"  • {t}")


# ── Argument parser ───────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Multi-Agent Competitive Intelligence & Market Research System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "OpenAI competitors"
  python main.py "Anthropic Claude" --format json
  python main.py "HR tech market" --format markdown
  python main.py --history
  python main.py --list-topics
        """,
    )
    p.add_argument("topic", nargs="?", help="Research topic")
    p.add_argument(
        "--format",
        choices=["rich", "json", "markdown"],
        default="rich",
        help="Output format (default: rich)",
    )
    p.add_argument("--history", action="store_true", help="Show recent query history")
    p.add_argument("--list-topics", action="store_true", help="List all researched topics")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose / debug logging")
    return p


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.history:
        asyncio.run(_show_history())
    elif args.list_topics:
        asyncio.run(_list_topics())
    elif args.topic:
        asyncio.run(_run_research(args.topic, args.format))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
