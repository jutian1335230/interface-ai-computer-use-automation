from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from interface_automation.policy import redact


class EvidenceRecorder:
    def __init__(self, root: Path, run_id: str) -> None:
        self.directory = root / run_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log_path = self.directory / "events.jsonl"

    def record(self, event: str, **payload: Any) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(redact(entry), default=str) + "\n")

    def write_json(self, name: str, value: object) -> Path:
        path = self.directory / name
        path.write_text(json.dumps(redact(value), indent=2, default=str), encoding="utf-8")
        return path


def new_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
