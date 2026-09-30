from __future__ import annotations

from typing import Any

from playwright.async_api import Locator as PlaywrightLocator
from playwright.async_api import Page

from interface_automation.models import ActionType, Locator, Step


class PlaywrightSurface:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def observe(self) -> dict[str, Any]:
        body = self.page.locator("body")
        return {
            "url": self.page.url,
            "title": await self.page.title(),
            "accessibility": (await body.aria_snapshot())[:12_000],
        }

    def locate(self, locator: Locator) -> PlaywrightLocator:
        if locator.strategy == "role":
            return self.page.get_by_role(locator.role, name=locator.value, exact=locator.exact)
        if locator.strategy == "label":
            return self.page.get_by_label(locator.value, exact=locator.exact)
        if locator.strategy == "text":
            return self.page.get_by_text(locator.value, exact=locator.exact)
        return self.page.locator(locator.value)

    async def execute(self, step: Step, value: str | None = None) -> str | None:
        if step.action == ActionType.NAVIGATE:
            await self.page.goto(value or step.value or "", wait_until="domcontentloaded", timeout=step.timeout_ms)
            return None
        if step.action == ActionType.WAIT:
            await self.page.wait_for_timeout(int(value or step.value or "500"))
            return None
        if step.locator is None:
            raise ValueError(f"{step.action} requires a locator")
        target = self.locate(step.locator)
        if step.action == ActionType.CLICK:
            await target.click(timeout=step.timeout_ms)
            await self.page.wait_for_load_state("domcontentloaded")
            return None
        if step.action == ActionType.FILL:
            await target.fill(value or step.value or "", timeout=step.timeout_ms)
            return None
        if step.action == ActionType.EXTRACT:
            return (await target.inner_text(timeout=step.timeout_ms)).strip()
        raise ValueError(f"unsupported action: {step.action}")