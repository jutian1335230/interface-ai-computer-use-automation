from __future__ import annotations

import re
from typing import Any, Literal, Protocol

from openai import AsyncOpenAI
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel

from interface_automation.evidence import EvidenceRecorder
from interface_automation.models import (
    ActionType,
    BusinessOutcomeRule,
    CapabilityArtifact,
    Checkpoint,
    Locator,
    OutputSpec,
    ParameterSpec,
    RiskLevel,
    Step,
)
from interface_automation.policy import Policy
from interface_automation.surface import PlaywrightSurface


class AgentDecision(BaseModel):
    action: Literal["navigate", "click", "fill", "extract", "done", "escalate"]
    description: str
    locator: Locator | None = None
    value: str | None = None
    output_name: str | None = None
    checkpoint: Locator | None = None
    reasoning: str


class Planner(Protocol):
    async def decide(
        self, goal: str, observation: dict[str, Any], history: list[dict[str, Any]]
    ) -> AgentDecision: ...


class OpenAIPlanner:
    def __init__(self, model: str = "gpt-4.1-mini") -> None:
        self.client = AsyncOpenAI()
        self.model = model

    async def decide(
        self, goal: str, observation: dict[str, Any], history: list[dict[str, Any]]
    ) -> AgentDecision:
        response = await self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Operate the UI one step at a time using the accessibility snapshot. Prefer role and label "
                        "locators, then text, and CSS only as a last resort. Extract requested data before done. "
                        "For extraction, target the exact value element structurally, never by its runtime value. "
                        "Never invent controls. Use escalate when blocked. Put a stable success locator in checkpoint "
                        "when done; checkpoints must identify page state, not runtime data. Do not include secrets or "
                        "personal data in reasoning."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Goal: {goal}\nObservation: {observation}\nPrior actions: {history[-8:]}",
                },
            ],
            text_format=AgentDecision,
        )
        if response.output_parsed is None:
            raise RuntimeError("model returned no structured decision")
        return response.output_parsed


class ScriptedDemoPlanner:
    """Offline smoke-test planner; it is explicitly not evidence of an LLM discovery run."""

    async def decide(
        self, goal: str, observation: dict[str, Any], history: list[dict[str, Any]]
    ) -> AgentDecision:
        decisions = [
            AgentDecision(
                action="fill", description="Enter member number",
                locator=Locator(strategy="label", value="Member number", rationale="Visible label is stable."),
                value="12345", reasoning="The goal identifies this training member."
            ),
            AgentDecision(
                action="click", description="Submit member lookup",
                locator=Locator(strategy="role", role="button", value="Find member", rationale="Role and name survive markup changes."),
                reasoning="Submit the completed lookup form."
            ),
            AgentDecision(
                action="extract", description="Read savings balance",
                locator=Locator(strategy="css", value="table[aria-label='Member account summary'] tr:nth-child(3) td", rationale="Scoped table row is stable in this legacy surface."),
                output_name="savings_balance", reasoning="Return the requested field."
            ),
            AgentDecision(
                action="done", description="Member balance was extracted",
                checkpoint=Locator(strategy="role", role="heading", value="Member Detail", rationale="Page heading confirms successful navigation."),
                reasoning="The goal is complete and the detail heading is visible."
            ),
        ]
        return decisions[min(len(history), len(decisions) - 1)]


class DiscoveryRunner:
    def __init__(self, surface: PlaywrightSurface, policy: Policy, evidence: EvidenceRecorder) -> None:
        self.surface = surface
        self.policy = policy
        self.evidence = evidence

    async def run(
        self,
        goal: str,
        target_url: str,
        planner: Planner,
        parameters: dict[str, object],
        max_steps: int = 10,
    ) -> CapabilityArtifact:
        history: list[dict[str, Any]] = []
        entry_step = Step(
            id="step-1",
            action=ActionType.NAVIGATE,
            description="Open the caller-provided target",
            value=target_url,
            risk=RiskLevel.SAFE,
        )
        recorded_steps: list[Step] = [entry_step]
        extracted_values: list[str] = []
        checkpoint: Locator | None = None
        self.policy.check_url(target_url)
        self.evidence.record("discovery_started", goal=goal, target=target_url, max_steps=max_steps)
        self.policy.check_step(entry_step)
        await self.surface.execute(entry_step, target_url)
        self.evidence.record("target_opened", step_id=entry_step.id)

        for index in range(max_steps):
            observation = await self.surface.observe()
            self.evidence.record("observation", step=index, observation=observation)
            decision = await planner.decide(goal, observation, history)
            self.evidence.record(
                "model_decision", step=index, action=decision.action, reasoning=decision.reasoning,
                description=decision.description
            )
            history.append(decision.model_dump(mode="json"))
            if decision.action == "done":
                checkpoint = self._stable_checkpoint(
                    decision.checkpoint,
                    observation,
                    [str(value) for value in parameters.values()] + extracted_values,
                )
                break
            if decision.action == "escalate":
                raise RuntimeError(f"discovery requested human help: {decision.reasoning}")

            action = ActionType(decision.action)
            stored_value = self._parameterize(decision.value, parameters)
            step = Step(
                id=f"step-{index + 2}",
                action=action,
                description=self._parameterize_all(decision.description, parameters),
                locator=decision.locator, value=stored_value, output=decision.output_name, risk=RiskLevel.SAFE
            )
            self.policy.check_step(step)
            execution_value = decision.value
            if action == ActionType.NAVIGATE:
                self.policy.check_url(execution_value or target_url)
            try:
                result = await self.surface.execute(step, execution_value)
            except PlaywrightError as exc:
                error = str(exc).split("\n", 1)[0]
                self.evidence.record("action_failed", step_id=step.id, action=action, observed=error)
                history.append(
                    {
                        "execution_error": error,
                        "instruction": "Choose a different locator or action from the current observation.",
                    }
                )
                continue
            if action == ActionType.EXTRACT and result is not None:
                extracted_values.append(result)
                output_label = (step.output or "value").replace("_", " ")
                step.description = f"Extract the {output_label} value"
                history.append(
                    {
                        "execution_result": {decision.output_name or "value": result},
                        "instruction": "The value was extracted successfully; finish if the goal is complete.",
                    }
                )
                if step.locator and result in step.locator.value:
                    step.locator = Locator(
                        strategy="css",
                        value=f'tr:has(th:has-text("{output_label}")) td',
                        rationale="Semantic row label avoids embedding the runtime output value.",
                    )
            self.policy.check_url(self.surface.page.url)
            recorded_steps.append(step)
        else:
            raise RuntimeError(f"discovery exceeded max_steps={max_steps}")

        if checkpoint is None:
            raise RuntimeError("discovery completed without a checkpoint")
        outputs = [
            OutputSpec(
                name=step.output,
                type="string",
                description=f"Extracted {step.output.replace('_', ' ')} value",
                sensitive=True,
            )
            for step in recorded_steps if step.output
        ]
        artifact = CapabilityArtifact(
            capability_id="member-savings-lookup",
            name="Look up member savings balance",
            description=self._parameterize_all(goal, parameters),
            target_url=target_url,
            allowed_route_pattern=r"/legacy(?:/.*)?",
            inputs=[
                ParameterSpec(
                    name=name,
                    type="string",
                    description=f"Runtime {name.replace('_', ' ')}",
                    sensitive=True,
                    pattern=r"\d{5}",
                ) for name in parameters
            ],
            outputs=outputs,
            steps=recorded_steps,
            checkpoint=Checkpoint(locator=checkpoint, description="The member detail view is visible"),
            business_outcomes=[
                BusinessOutcomeRule(
                    code="member_not_found",
                    locator=Locator(
                        strategy="text",
                        value="No member found",
                        rationale="The server-rendered outcome has stable, user-visible copy.",
                    ),
                    message="No member matched the supplied member number",
                )
            ],
        )
        self.evidence.write_json("artifact.json", artifact.model_dump(mode="json"))
        self.evidence.record("discovery_completed", capability_id=artifact.capability_id)
        return artifact

    @staticmethod
    def _parameterize(value: str | None, parameters: dict[str, object]) -> str | None:
        if value is None:
            return None
        for name, parameter in parameters.items():
            if value == str(parameter):
                return "{{" + name + "}}"
        return value

    @staticmethod
    def _parameterize_all(value: str, parameters: dict[str, object]) -> str:
        for name, parameter in parameters.items():
            value = value.replace(str(parameter), "{{" + name + "}}")
        return value

    @staticmethod
    def _stable_checkpoint(
        checkpoint: Locator | None, observation: dict[str, Any], runtime_values: list[str]
    ) -> Locator | None:
        if checkpoint is None:
            return None
        headings = re.findall(r'heading "([^"]+)"', str(observation.get("accessibility", "")))
        contains_runtime_value = any(value and value in checkpoint.value for value in runtime_values)
        invalid_heading = checkpoint.strategy == "role" and checkpoint.role == "heading" and checkpoint.value not in headings
        if not contains_runtime_value and not invalid_heading:
            return checkpoint
        if not headings:
            return None
        return Locator(
            strategy="role",
            role="heading",
            value=headings[0],
            rationale="Stable page heading replaces a runtime-data checkpoint.",
        )