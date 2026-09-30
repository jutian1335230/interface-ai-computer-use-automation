from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from rich.console import Console

from interface_automation.discovery import DiscoveryRunner, OpenAIPlanner, ScriptedDemoPlanner
from interface_automation.evidence import EvidenceRecorder, new_run_id
from interface_automation.handoff import InterventionManager
from interface_automation.models import CapabilityArtifact
from interface_automation.policy import Policy
from interface_automation.replay import ReplayEngine
from interface_automation.surface import PlaywrightSurface

app = typer.Typer(help="Discover and replay safe UI automation capabilities.", no_args_is_help=True)
console = Console()
load_dotenv()
ROOT = Path.cwd()
EVIDENCE = ROOT / "evidence"
INTERVENTIONS = EVIDENCE / "interventions"


def parse_parameters(items: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter(f"parameter must be NAME=VALUE: {item}")
        key, value = item.split("=", 1)
        result[key] = value
    return result


async def run_discovery(
    goal: str,
    target: str,
    parameters: dict[str, object],
    output: Path,
    offline: bool,
    headless: bool,
) -> CapabilityArtifact:
    recorder = EvidenceRecorder(EVIDENCE, new_run_id("discovery-offline" if offline else "discovery-live"))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        runner = DiscoveryRunner(PlaywrightSurface(page), Policy(), recorder)
        planner = ScriptedDemoPlanner() if offline else OpenAIPlanner(os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
        artifact = await runner.run(goal, target, planner, parameters)
        await page.screenshot(path=str(recorder.directory / "final.png"), full_page=True)
        await browser.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"Artifact: [bold]{output}[/bold]")
    console.print(f"Evidence: [bold]{recorder.directory}[/bold]")
    return artifact


async def run_replay(
    artifact: CapabilityArtifact,
    parameters: dict[str, object],
    *,
    headless: bool,
    handoff_at: str | None = None,
    wait_for_human: bool = False,
    keep_open_seconds: int = 0,
    prefix: str = "replay",
) -> object:
    recorder = EvidenceRecorder(EVIDENCE, new_run_id(prefix))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        await context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = await context.new_page()
        engine = ReplayEngine(
            PlaywrightSurface(page), Policy(), recorder, InterventionManager(INTERVENTIONS)
        )
        result = await engine.run(
            artifact, parameters, handoff_at=handoff_at, wait_for_human=wait_for_human
        )
        await context.tracing.stop(path=str(recorder.directory / "trace.zip"))
        if not headless and keep_open_seconds:
            console.print(f"Replay complete; keeping browser open for {keep_open_seconds} seconds.")
            await asyncio.sleep(keep_open_seconds)
        if not (wait_for_human and handoff_at):
            await browser.close()
    recorder.write_json("result.json", result.model_dump(mode="json"))
    console.print_json(result.model_dump_json(indent=2))
    return result


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port.")] = 8000,
) -> None:
    """Run the intentionally legacy-style training application."""
    uvicorn.run("interface_automation.target_app:app", host=host, port=port, log_level="warning")


@app.command()
def discover(
    goal: Annotated[str, typer.Option(help="Natural-language task for the agent.")],
    target: Annotated[str, typer.Option(help="Allowlisted application entry point.")] = "http://127.0.0.1:8000/legacy",
    param: Annotated[list[str], typer.Option("--param", help="Runtime input as NAME=VALUE.")] = [],
    output: Annotated[Path, typer.Option(help="Artifact destination.")] = Path("evidence/example-artifact.json"),
    offline: Annotated[bool, typer.Option(help="Use the deterministic smoke-test planner; not valid LLM evidence.")] = False,
    headed: Annotated[bool, typer.Option(help="Show the browser.")] = False,
) -> None:
    """Run observe-decide-act discovery and compile the successful trace."""
    if not offline and not os.getenv("OPENAI_API_KEY"):
        raise typer.BadParameter("OPENAI_API_KEY is required unless --offline is supplied")
    asyncio.run(run_discovery(goal, target, parse_parameters(param), output, offline, not headed))


@app.command()
def replay(
    artifact_path: Annotated[Path, typer.Argument(help="Saved capability artifact.")],
    param: Annotated[list[str], typer.Option("--param", help="Runtime input as NAME=VALUE.")] = [],
    headed: Annotated[bool, typer.Option(help="Show the browser.")] = False,
    keep_open_seconds: Annotated[
        int, typer.Option(min=0, help="Keep a headed browser open after replay completes.")
    ] = 0,
    handoff_at: Annotated[str | None, typer.Option(help="Pause before this step for a human.")] = None,
    wait_for_human: Annotated[bool, typer.Option(help="Wait for the resume command on the live session.")] = False,
) -> None:
    """Replay an artifact without an LLM in the decision loop."""
    artifact = CapabilityArtifact.model_validate_json(artifact_path.read_text(encoding="utf-8"))
    asyncio.run(
        run_replay(
            artifact,
            parse_parameters(param),
            headless=not headed,
            handoff_at=handoff_at,
            wait_for_human=wait_for_human,
            keep_open_seconds=keep_open_seconds,
        )
    )


@app.command()
def resume(
    intervention_id: Annotated[str, typer.Argument(help="Intervention request ID.")],
    note: Annotated[str, typer.Option(help="Non-sensitive summary of the manual action.")] = "Operator completed review",
) -> None:
    """Return control of a paused live browser session to automation."""
    path = InterventionManager(INTERVENTIONS).resume(intervention_id, note)
    console.print(f"Resume signal written: {path}")


def start_demo_server() -> None:
    thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": "interface_automation.target_app:app",
            "host": "127.0.0.1",
            "port": 8000,
            "log_level": "warning",
        },
        daemon=True,
    )
    thread.start()
    for _ in range(40):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/legacy", timeout=0.25).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("demo server did not start")


@app.command()
def demo() -> None:
    """Generate reproducible offline discovery and replay evidence."""
    start_demo_server()
    artifact_path = EVIDENCE / "example-artifact.json"

    async def workflow() -> None:
        artifact = await run_discovery(
            "Look up member 12345 and read the current savings balance",
            "http://127.0.0.1:8000/legacy",
            {"member_id": "12345"},
            artifact_path,
            offline=True,
            headless=True,
        )
        await run_replay(artifact, {"member_id": "12345"}, headless=True, prefix="replay-success")
        await run_replay(artifact, {"member_id": "11111"}, headless=True, prefix="replay-not-found")

    asyncio.run(workflow())


if __name__ == "__main__":
    app()