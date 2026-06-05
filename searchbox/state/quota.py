"""Provider daily and monthly quota state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from .json_store import read_json_file_locked, write_json_file_locked


def quota_day() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def quota_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


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
        raise HTTPException(status_code=429, detail={
            "source": provider,
            "reason": "advanced_provider_disabled_by_monthly_limit",
            "message": f"{provider} monthly request limit is disabled or set to zero.",
            "monthly_limit": limit,
            "used_this_month": 0,
            "requested_units": units,
        })

    month = quota_month()
    now = datetime.utcnow()
    next_month = datetime(now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1)
    retry_after = max(1, int((next_month - now).total_seconds()))

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        current_counts = data.get(month, {}) if isinstance(data.get(month), dict) else {}
        data.clear()
        data[month] = current_counts
        used = int(data[month].get(provider, 0) or 0)
        if used + units > limit:
            raise HTTPException(status_code=429, detail={
                "source": provider,
                "reason": "advanced_provider_monthly_limit_reached",
                "message": f"{provider} monthly provider limit reached inside Searchbox.",
                "monthly_limit": limit,
                "used_this_month": used,
                "requested_units": units,
                "retry_after_seconds": retry_after,
            }, headers={"Retry-After": str(retry_after)})
        data[month][provider] = used + units
        return {}

    write_json_file_locked(quota_file, mutate)


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
    reserve_monthly(provider, monthly_quota_file, monthly_limits, units)
    limit = int(limits.get(provider, 0) or 0)
    if limit <= 0:
        raise HTTPException(status_code=429, detail={
            "source": provider,
            "reason": "advanced_provider_disabled_by_daily_limit",
            "message": f"{provider} daily request limit is disabled or set to zero.",
            "daily_limit": limit,
            "used_today": 0,
            "requested_units": units,
        })

    day = quota_day()

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        current_counts = data.get(day, {}) if isinstance(data.get(day), dict) else {}
        data.clear()
        data[day] = current_counts
        used = int(data[day].get(provider, 0) or 0)
        if used + units > limit:
            now = datetime.utcnow()
            retry_after = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
            raise HTTPException(status_code=429, detail={
                "source": provider,
                "reason": "advanced_provider_daily_limit_reached",
                "message": f"{provider} daily free/provider limit reached inside Searchbox.",
                "daily_limit": limit,
                "used_today": used,
                "requested_units": units,
                "retry_after_seconds": retry_after,
            }, headers={"Retry-After": str(retry_after)})
        data[day][provider] = used + units
        return {}

    write_json_file_locked(quota_file, mutate)
