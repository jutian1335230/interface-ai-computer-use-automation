from pydantic import TypeAdapter, ValidationError

from interface_automation.models import (
    BusinessOutcomeResult,
    FailureResult,
    Locator,
    RunResult,
    StepFailure,
    SuccessResult,
)


def test_result_contract_is_discriminated_by_status() -> None:
    adapter = TypeAdapter(RunResult)

    success = adapter.validate_python(
        {"status": "success", "outputs": {"balance": "$1,250.00"}, "evidence_dir": "run-1"}
    )
    outcome = adapter.validate_python(
        {
            "status": "business_outcome",
            "code": "member_not_found",
            "message": "No member matched",
            "evidence_dir": "run-2",
        }
    )
    failure = adapter.validate_python(
        {
            "status": "failure",
            "code": "checkpoint_failed",
            "message": "Expected detail page",
            "detail": {"expected": "Member detail", "observed": "Session expired"},
            "evidence_dir": "run-3",
        }
    )

    assert isinstance(success, SuccessResult)
    assert isinstance(outcome, BusinessOutcomeResult)
    assert isinstance(failure, FailureResult)


def test_role_locator_requires_a_role() -> None:
    try:
        Locator(strategy="role", value="Search", rationale="Accessible name is stable")
    except ValidationError:
        return
    raise AssertionError("role locator without role should be rejected")


def test_failure_requires_debuggable_detail() -> None:
    result = FailureResult(
        code="action_failed",
        message="Could not click",
        detail=StepFailure(step_id="open-member", expected="button", observed="dialog"),
        evidence_dir="evidence/run",
    )
    assert result.detail.step_id == "open-member"