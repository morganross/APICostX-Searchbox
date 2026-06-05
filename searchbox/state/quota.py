"""Provider daily and monthly quota state."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .json_store import file_paths, read_json_file_locked, write_json_file_locked


def quota_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def quota_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _snapshot_for_period(quota_file: str, period: str, limits: dict[str, int]) -> dict[str, Any]:
    data = read_json_file_locked(quota_file)
    counts = data.get(period) if isinstance(data.get(period), dict) else {}
    return {
        provider: {
            "used": int(counts.get(provider, 0) or 0),
            "limit": int(limit),
            "remaining": max(0, int(limit) - int(counts.get(provider, 0) or 0)),
        }
        for provider, limit in limits.items()
    }


def monthly_snapshot(quota_file: str, limits: dict[str, int]) -> dict[str, Any]:
    return _snapshot_for_period(quota_file, quota_month(), limits)


def daily_snapshot(quota_file: str, limits: dict[str, int]) -> dict[str, Any]:
    return _snapshot_for_period(quota_file, quota_day(), limits)


def reserve_monthly(provider: str, quota_file: str, limits: dict[str, int], units: int = 1) -> None:
    units = max(1, int(units or 1))
    if provider not in limits:
        return
    limit = int(limits.get(provider, 0) or 0)
    if limit <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "source": provider,
                "reason": "advanced_provider_disabled_by_monthly_limit",
                "message": f"{provider} monthly request limit is disabled or set to zero.",
                "monthly_limit": limit,
                "used_this_month": 0,
                "requested_units": units,
            },
        )

    month = quota_month()
    now = datetime.now(timezone.utc)
    next_month = datetime(
        now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1, tzinfo=timezone.utc
    )
    retry_after = max(1, int((next_month - now).total_seconds()))

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        current_counts = data.get(month, {}) if isinstance(data.get(month), dict) else {}
        data.clear()
        data[month] = current_counts
        used = int(data[month].get(provider, 0) or 0)
        if used + units > limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "source": provider,
                    "reason": "advanced_provider_monthly_limit_reached",
                    "message": f"{provider} monthly provider limit reached inside Searchbox.",
                    "monthly_limit": limit,
                    "used_this_month": used,
                    "requested_units": units,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        data[month][provider] = used + units
        return data

    write_json_file_locked(quota_file, mutate)


def _read_json_unlocked(data_file: str) -> dict[str, Any]:
    try:
        with open(data_file, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def _write_json_unlocked(data_file: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
    tmp_file = data_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True)
    os.replace(tmp_file, data_file)


def _raise_daily_limit(provider: str, limit: int, used: int, units: int) -> None:
    now = datetime.now(timezone.utc)
    retry_after = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
    raise HTTPException(
        status_code=429,
        detail={
            "source": provider,
            "reason": "advanced_provider_daily_limit_reached",
            "message": f"{provider} daily free/provider limit reached inside Searchbox.",
            "daily_limit": limit,
            "used_today": used,
            "requested_units": units,
            "retry_after_seconds": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


def reserve_daily(
    provider: str,
    quota_file: str,
    limits: dict[str, int],
    *,
    monthly_quota_file: str,
    monthly_limits: dict[str, int],
    units: int = 1,
) -> None:
    units = max(1, int(units or 1))
    limit = int(limits.get(provider, 0) or 0)
    if limit <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "source": provider,
                "reason": "advanced_provider_disabled_by_daily_limit",
                "message": f"{provider} daily request limit is disabled or set to zero.",
                "daily_limit": limit,
                "used_today": 0,
                "requested_units": units,
            },
        )

    if provider not in monthly_limits:

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            day = quota_day()
            current_counts = data.get(day, {}) if isinstance(data.get(day), dict) else {}
            data.clear()
            data[day] = current_counts
            used = int(data[day].get(provider, 0) or 0)
            if used + units > limit:
                _raise_daily_limit(provider, limit, used, units)
            data[day][provider] = used + units
            return data

        write_json_file_locked(quota_file, mutate)
        return

    monthly_limit = int(monthly_limits.get(provider, 0) or 0)
    if monthly_limit <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "source": provider,
                "reason": "advanced_provider_disabled_by_monthly_limit",
                "message": f"{provider} monthly request limit is disabled or set to zero.",
                "monthly_limit": monthly_limit,
                "used_this_month": 0,
                "requested_units": units,
            },
        )

    day = quota_day()
    month = quota_month()
    now = datetime.now(timezone.utc)
    next_month = datetime(
        now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1, tzinfo=timezone.utc
    )
    monthly_retry_after = max(1, int((next_month - now).total_seconds()))

    daily_data_file, daily_lock_file = file_paths(quota_file)
    monthly_data_file, monthly_lock_file = file_paths(monthly_quota_file)
    locks = [open(lock_file, "a+", encoding="utf-8") for lock_file in sorted({daily_lock_file, monthly_lock_file})]
    try:
        for lock in locks:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        daily_data = _read_json_unlocked(daily_data_file)
        monthly_data = daily_data if daily_data_file == monthly_data_file else _read_json_unlocked(monthly_data_file)
        daily_counts = daily_data.get(day, {}) if isinstance(daily_data.get(day), dict) else {}
        monthly_counts = monthly_data.get(month, {}) if isinstance(monthly_data.get(month), dict) else {}
        daily_used = int(daily_counts.get(provider, 0) or 0)
        monthly_used = int(monthly_counts.get(provider, 0) or 0)

        if daily_used + units > limit:
            _raise_daily_limit(provider, limit, daily_used, units)
        if monthly_used + units > monthly_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "source": provider,
                    "reason": "advanced_provider_monthly_limit_reached",
                    "message": f"{provider} monthly provider limit reached inside Searchbox.",
                    "monthly_limit": monthly_limit,
                    "used_this_month": monthly_used,
                    "requested_units": units,
                    "retry_after_seconds": monthly_retry_after,
                },
                headers={"Retry-After": str(monthly_retry_after)},
            )

        daily_data.clear()
        daily_data[day] = daily_counts
        daily_data[day][provider] = daily_used + units
        monthly_data.clear()
        monthly_data[month] = monthly_counts
        monthly_data[month][provider] = monthly_used + units

        _write_json_unlocked(daily_data_file, daily_data)
        if monthly_data_file != daily_data_file:
            _write_json_unlocked(monthly_data_file, monthly_data)
    finally:
        for lock in reversed(locks):
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            finally:
                lock.close()
