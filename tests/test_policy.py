import pytest

from interface_automation.models import ActionType, RiskLevel, Step
from interface_automation.policy import Policy, PolicyViolation, redact
from interface_automation.replay import render


def test_policy_rejects_external_origin_and_route() -> None:
    policy = Policy()
    with pytest.raises(PolicyViolation, match="origin"):
        policy.check_url("https://example.com/legacy")
    with pytest.raises(PolicyViolation, match="route"):
        policy.check_url("http://127.0.0.1:8000/admin")


def test_irreversible_action_requires_confirmation() -> None:
    step = Step(
        id="transfer",
        action=ActionType.CLICK,
        description="Submit transfer",
        risk=RiskLevel.IRREVERSIBLE,
    )
    with pytest.raises(PolicyViolation, match="confirmation"):
        Policy().check_step(step)


def test_redaction_masks_sensitive_keys_and_member_numbers() -> None:
    value = redact({"token": "abc", "message": "member 12345 loaded"})
    assert value == {"token": "[REDACTED]", "message": "member ***45 loaded"}


def test_parameter_rendering_rejects_unresolved_values() -> None:
    assert render("{{member_id}}", {"member_id": "12345"}) == "12345"
    with pytest.raises(ValueError, match="unresolved"):
        render("{{missing}}", {})