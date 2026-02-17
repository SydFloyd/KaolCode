from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def ensure_job_artifact_dir(root: str, job_id: str) -> Path:
    path = Path(root) / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def ensure_contract(path: Path, contract: Iterable[str]) -> None:
    for name in contract:
        target = path / name
        if not target.exists():
            target.write_text("", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

