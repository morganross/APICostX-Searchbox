"""Small logging helpers used by Searchbox runtime code."""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime
from typing import Any


def json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def append_jsonl(path: str, event: dict[str, Any]) -> None:
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        event = {str(k): json_safe(v) for k, v in dict(event or {}).items()}
        event.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception:
        return


def tail_jsonl(path: str, max_lines: int) -> list[dict[str, Any]]:
    if not path or not os.path.exists(path):
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=max(1, int(max_lines or 1)))
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return list(rows)


def summarize_events(events: list[dict[str, Any]], group_fields: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {"total": len(events), "groups": {}}
    for event in events:
        key = "|".join(str(event.get(field) or "unknown") for field in group_fields)
        group = summary["groups"].setdefault(key, {"total": 0, "success": 0, "failure": 0, "last_event": None})
        group["total"] += 1
        if event.get("success") is True:
            group["success"] += 1
        elif event.get("success") is False:
            group["failure"] += 1
        group["last_event"] = event.get("timestamp")
    return summary
