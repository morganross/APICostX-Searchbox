"""Authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class AuthSettings:
    auth_disabled: bool
    search_api_key: str


def auth_key_from_header_or_key(
    authorization: str | None,
    api_key: str | None = None,
    *,
    settings: AuthSettings,
) -> str:
    if settings.auth_disabled:
        return "anonymous"
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
    elif api_key:
        token = api_key.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing API key or bearer token")

    if not settings.search_api_key:
        raise HTTPException(status_code=503, detail="SEARCH_API_KEY is not configured")

    if token != settings.search_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return "authorized"
