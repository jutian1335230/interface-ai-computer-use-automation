from __future__ import annotations

import re
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from interface_automation.evidence import EvidenceRecorder
from interface_automation.handoff import InterventionManager
from interface_automation.models import (
    BusinessOutcomeResult,
    CapabilityArtifact,
    FailureResult,
    RunResult,
    Step,
    StepFailure,
    SuccessResult,
)
from interface_automation.policy import Policy, PolicyViolation
from interface_automation.surface import PlaywrightSurface


def render(template: str | None, parameters: dict[str, object]) -> str | None:
    if template is None:
        return None
    rendered = template
    for key, value in parameters.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    if re.search(r"{{[^}]+}}", rendered):
        raise ValueError(f"unresolved parameter in {rendered!r}")
    return rendered


class ReplayEngine:
    def __init__(
        self,
        surface: PlaywrightSurface,
        policy: Policy,
        evidence: EvidenceRecorder,
        interventions: InterventionManager,
    ) -> None:
        self.surface = surface
        self.policy = policy
        self.evidence = evidence
        self.interventions = interventions

    async def run(
        self,
        artifact: CapabilityArtifact,
        parameters: dict[str, object],
        *,
        handoff_at: str | None = None,
        wait_for_human: bool = False,
    ) -> RunResult:
        try:
            self.policy.check_url(str(artifact.target_url))
            self._validate_parameters(artifact, parameters)
        except (PolicyViolation, ValueError) as exc:
            return self._failure("policy_or_input", str(exc), None, "valid policy and inputs", str(exc))

        outputs: dict[str, object] = {}
        self.evidence.record(
            "replay_started", capability_id=artifact.capability_id, artifact_version=artifact.artifact_version
        )
        for step in artifact.steps:
            if handoff_at == step.id:
                request = await self.interventions.request(
                    self.surface.page, self.evidence, artifact.capability_id, "configured human checkpoint", step.id
                )
                if not wait_for_human:
                    return self._failure(
                        "human_required",
                        "automation paused for operator",
                        step.id,
                        "operator resumes the live session",
                        "control transferred to human",
                        request.id,
                    )
                if not await self.interventions.wait_for_resume(request, self.surface.page, self.evidence):
                    return self._failure(
                        "human_timeout", "operator did not resume in time", step.id, "resume signal", "timeout", request.id
                    )
                continue

            result = await self._run_step(artifact, step, parameters)
            if isinstance(result, (BusinessOutcomeResult, FailureResult)):
                return result
            if result is not None and step.output:
                outputs[step.output] = result

        checkpoint = self.surface.locate(artifact.checkpoint.locator)
        try:
            await checkpoint.wait_for(state="visible", timeout=5_000)
            if artifact.checkpoint.expected_text:
                observed = (await checkpoint.inner_text()).strip()
                if artifact.checkpoint.expected_text not in observed:
                    raise AssertionError(f"checkpoint text was {observed!r}")
        except (PlaywrightError, AssertionError) as exc:
            return await self._failure_with_screenshot(
                "checkpoint_failed",
                "final checkpoint was not satisfied",
                artifact.steps[-1].id if artifact.steps else None,
                artifact.checkpoint.description,
                str(exc),
            )
        self.evidence.record("replay_completed", status="success", outputs=outputs)
        return SuccessResult(outputs=outputs, evidence_dir=str(self.evidence.directory))

    async def _run_step(
        self, artifact: CapabilityArtifact, step: Step, parameters: dict[str, object]
    ) -> str | BusinessOutcomeResult | FailureResult | None:
        try:
            self.policy.check_step(step)
            value = render(step.value, parameters)
            self.evidence.record("step_started", step_id=step.id, action=step.action, description=step.description)
            result = None
            for attempt in range(step.retries + 1):
                try:
                    result = await self.surface.execute(step, value)
                    break
                except PlaywrightError:
                    if attempt == step.retries:
                        raise
                    self.evidence.record("step_retry", step_id=step.id, attempt=attempt + 1)
            self.policy.check_url(self.surface.page.url)
            self.evidence.record("step_completed", step_id=step.id)
            for rule in artifact.business_outcomes:
                target = self.surface.locate(rule.locator)
                if await target.count() and await target.first.is_visible():
                    self.evidence.record("business_outcome", code=rule.code, step_id=step.id)
                    return BusinessOutcomeResult(
                        code=rule.code, message=rule.message, evidence_dir=str(self.evidence.directory)
                    )
            if await self.surface.page.get_by_role("heading", name="Session expired").count():
                return await self._failure_with_screenshot(
                    "session_expired", "session expired during replay", step.id, "active session", "Session expired"
                )
            return result
        except (PlaywrightError, PolicyViolation, ValueError) as exc:
            return await self._failure_with_screenshot(
                "step_failed", f"step {step.id} failed", step.id, step.description, str(exc)
            )

    def _validate_parameters(self, artifact: CapabilityArtifact, parameters: dict[str, object]) -> None:
        for spec in artifact.inputs:
            if spec.required and spec.name not in parameters:
                raise ValueError(f"missing required parameter: {spec.name}")
            if spec.name in parameters and spec.pattern and not re.fullmatch(spec.pattern, str(parameters[spec.name])):
                raise ValueError(f"parameter {spec.name} does not match {spec.pattern}")

    async def _failure_with_screenshot(
        self, code: str, message: str, step_id: str | None, expected: str, observed: str
    ) -> FailureResult:
        screenshot = self.evidence.directory / f"failure-{step_id or 'run'}.png"
        await self.surface.page.screenshot(path=str(screenshot), full_page=True)
        return self._failure(code, message, step_id, expected, observed, screenshot=str(screenshot))

    def _failure(
        self,
        code: str,
        message: str,
        step_id: str | None,
        expected: str,
        observed: str,
        intervention_id: str | None = None,
        screenshot: str | None = None,
    ) -> FailureResult:
        self.evidence.record("replay_failed", code=code, step_id=step_id, expected=expected, observed=observed)
        return FailureResult(
            code=code,
            message=message,
            detail=StepFailure(step_id=step_id, expected=expected, observed=observed, screenshot=screenshot),
            intervention_id=intervention_id,
            evidence_dir=str(self.evidence.directory),
        )
