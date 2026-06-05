"""Provider cooldown state and backoff behavior."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .json_store import read_json_file_locked, write_json_file_locked


def base_cooldown_seconds(provider: str, status_code: int, *, arxiv_cooldown_seconds: float) -> int:
    if status_code == 402:
        return 86400
    if status_code == 429:
        return 900 if provider != "arxiv" else int(arxiv_cooldown_seconds)
    if status_code == 503:
        return 900
    if status_code in (502, 504):
        return 300
    return 120


def snapshot(cooldown_file: str, provider_names: list[str]) -> dict[str, Any]:
    now = time.time()
    data = read_json_file_locked(cooldown_file)
    result: dict[str, Any] = {}
    for provider in provider_names:
        entry = data.get(provider) if isinstance(data.get(provider), dict) else {}
        until = float(entry.get("cooldown_until_epoch") or 0)
        remaining = max(0, int(round(until - now)))
        result[provider] = {
            "cooling_down": remaining > 0,
            "retry_after_seconds": remaining,
            "failure_count": int(entry.get("failure_count") or 0),
            "last_status_code": entry.get("last_status_code"),
            "last_reason": entry.get("last_reason"),
            "last_failure_at": entry.get("last_failure_at"),
        }
    return result


def remaining(cooldown_file: str, provider_names: list[str], provider: str) -> int:
    entry = snapshot(cooldown_file, provider_names).get(provider) or {}
    return int(entry.get("retry_after_seconds") or 0)


def raise_if_cooling(cooldown_file: str, provider_names: list[str], provider: str) -> None:
    retry_after = remaining(cooldown_file, provider_names, provider)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail={
                "source": provider,
                "reason": "advanced_provider_cooldown_active",
                "message": f"{provider} is cooling down locally after a recent provider failure.",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


def mark_success(cooldown_file: str, provider: str, log_event: Callable[[dict[str, Any]], None]) -> None:
    log_event({"event": "success", "provider": provider, "success": True})

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entry = data.get(provider) if isinstance(data.get(provider), dict) else {}
        entry.update(
            {
                "cooldown_until_epoch": 0,
                "failure_count": 0,
                "last_success_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        data[provider] = entry
        return data

    write_json_file_locked(cooldown_file, mutate)


def mark_failure(
    cooldown_file: str,
    provider: str,
    status_code: int,
    reason: str,
    *,
    max_cooldown_seconds: int,
    arxiv_cooldown_seconds: float,
    log_event: Callable[[dict[str, Any]], None],
    retry_after: int | None = None,
) -> int:
    now = time.time()

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        entry = data.get(provider) if isinstance(data.get(provider), dict) else {}
        failure_count = int(entry.get("failure_count") or 0) + 1
        base = (
            int(retry_after)
            if retry_after is not None
            else base_cooldown_seconds(
                provider,
                status_code,
                arxiv_cooldown_seconds=arxiv_cooldown_seconds,
            )
        )
        cooldown = min(max_cooldown_seconds, max(30, base * (2 ** max(0, failure_count - 1))))
        entry.update(
            {
                "cooldown_until_epoch": now + cooldown,
                "failure_count": failure_count,
                "last_status_code": status_code,
                "last_reason": reason,
                "last_failure_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        data[provider] = entry
        entry["retry_after_seconds"] = int(cooldown)
        data[provider] = entry
        return data

    result = write_json_file_locked(cooldown_file, mutate)
    provider_state = result.get(provider, {}) if isinstance(result, dict) else {}
    retry_seconds = int(
        provider_state.get("retry_after_seconds")
        or base_cooldown_seconds(provider, status_code, arxiv_cooldown_seconds=arxiv_cooldown_seconds)
    )
    log_event(
        {
            "event": "failure",
            "provider": provider,
            "success": False,
            "status_code": status_code,
            "reason": reason,
            "retry_after_seconds": retry_seconds,
            "failure_count": provider_state.get("failure_count"),
        }
    )
    return retry_seconds
