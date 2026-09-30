from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from interface_automation.models import ActionType, RiskLevel, Step


class PolicyViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class Policy:
    allowed_origins: frozenset[str] = frozenset({"http://127.0.0.1:8000", "http://localhost:8000"})
    allowed_route_patterns: tuple[str, ...] = (r"/legacy(?:/.*)?",)
    allowed_actions: frozenset[ActionType] = field(default_factory=lambda: frozenset(ActionType))
    require_confirmation_for: frozenset[RiskLevel] = frozenset({RiskLevel.IRREVERSIBLE})

    def check_url(self, url: str) -> None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.allowed_origins:
            raise PolicyViolation(f"origin is not allowlisted: {origin}")
        if not any(re.fullmatch(pattern, parsed.path) for pattern in self.allowed_route_patterns):
            raise PolicyViolation(f"route is not allowlisted: {parsed.path}")

    def check_step(self, step: Step, *, confirmed: bool = False) -> None:
        if step.action not in self.allowed_actions:
            raise PolicyViolation(f"action is not allowlisted: {step.action}")
        if step.risk in self.require_confirmation_for and not confirmed:
            raise PolicyViolation(f"human confirmation required for {step.risk} action")


SENSITIVE_KEY = re.compile(
    r"(password|secret|token|authorization|ssn|account|member|balance)", re.IGNORECASE
)
MEMBER_NUMBER = re.compile(r"(?<!\d)\d{5,}(?!\d)")


def redact(value: object, key: str = "") -> object:
    if SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return MEMBER_NUMBER.sub(lambda match: f"***{match.group()[-2:]}", value)
    return value
