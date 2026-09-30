import json

import pytest

from interface_automation.handoff import InterventionManager


def test_resume_signal_requires_an_existing_intervention(tmp_path) -> None:
    manager = InterventionManager(tmp_path)
    with pytest.raises(FileNotFoundError, match="unknown intervention"):
        manager.resume("missing", "done")


def test_resume_signal_records_operator_note(tmp_path) -> None:
    manager = InterventionManager(tmp_path)
    (tmp_path / "request-1.json").write_text("{}", encoding="utf-8")

    path = manager.resume("request-1", "Reviewed confirmation")

    assert json.loads(path.read_text(encoding="utf-8")) == {"note": "Reviewed confirmation"}