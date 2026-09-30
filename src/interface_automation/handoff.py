from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from playwright.async_api import Page

from interface_automation.evidence import EvidenceRecorder
from interface_automation.models import InterventionRequest


CAPTURE_SCRIPT = """
(() => {
  if (window.__operatorCaptureInstalled) return;
  window.__operatorCaptureInstalled = true;
  const record = (kind, target) => {
    const events = JSON.parse(sessionStorage.getItem('operatorEvents') || '[]');
    events.push({kind, tag: target.tagName, label: target.innerText || target.labels?.[0]?.innerText || target.name || ''});
    sessionStorage.setItem('operatorEvents', JSON.stringify(events.slice(-100)));
  };
  document.addEventListener('click', event => record('click', event.target), true);
  document.addEventListener('change', event => record('change', event.target), true);
})();
"""


class InterventionManager:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    async def request(
        self,
        page: Page,
        evidence: EvidenceRecorder,
        capability_id: str,
        reason: str,
        step_id: str | None,
    ) -> InterventionRequest:
        intervention_id = uuid4().hex[:12]
        screenshot = evidence.directory / f"intervention-{intervention_id}.png"
        await page.screenshot(path=str(screenshot), full_page=True)
        await page.add_init_script(CAPTURE_SCRIPT)
        await page.evaluate(CAPTURE_SCRIPT)
        request = InterventionRequest(
            id=intervention_id,
            capability_id=capability_id,
            reason=reason,
            step_id=step_id,
            screenshot=str(screenshot),
            control="human",
        )
        (self.directory / f"{intervention_id}.json").write_text(
            request.model_dump_json(indent=2), encoding="utf-8"
        )
        evidence.record("control_transferred", intervention_id=intervention_id, owner="human", reason=reason)
        return request

    async def wait_for_resume(
        self,
        request: InterventionRequest,
        page: Page,
        evidence: EvidenceRecorder,
        timeout_seconds: int = 300,
    ) -> bool:
        resume_path = self.directory / f"{request.id}.resume.json"
        for _ in range(timeout_seconds * 2):
            if resume_path.exists():
                note = json.loads(resume_path.read_text(encoding="utf-8"))
                events = await page.evaluate(
                    "JSON.parse(sessionStorage.getItem('operatorEvents') || '[]')"
                )
                evidence.record("human_actions", actions=events, operator_note=note.get("note", ""))
                evidence.record("control_transferred", intervention_id=request.id, owner="automation")
                return True
            await asyncio.sleep(0.5)
        evidence.record("intervention_timeout", intervention_id=request.id)
        return False

    def resume(self, intervention_id: str, note: str) -> Path:
        request_path = self.directory / f"{intervention_id}.json"
        if not request_path.exists():
            raise FileNotFoundError(f"unknown intervention: {intervention_id}")
        path = self.directory / f"{intervention_id}.resume.json"
        path.write_text(json.dumps({"note": note}, indent=2), encoding="utf-8")
        return path
