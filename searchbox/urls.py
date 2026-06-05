"""URL and domain safety helpers."""

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException


def favicon_for_url(url: str) -> str | None:
    host = (urlparse(url or "").netloc or "").lower()
    if not host:
        return None
    return f"https://www.google.com/s2/favicons?domain={host}&sz=64"


def is_private_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved


def validate_fetch_url(url: str, *, block_private_fetch_ips: bool = True) -> None:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail=f"Unsafe URL scheme or host: {url}")
    if not block_private_fetch_ips:
        return
    try:
        infos = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f"Could not resolve URL host: {parsed.hostname}") from exc
    for info in infos:
        if is_private_ip(info[4][0]):
            raise HTTPException(status_code=400, detail=f"Blocked private or unsafe fetch host: {parsed.hostname}")


def domain_allowed(url: str, include_domains: list[str], exclude_domains: list[str]) -> bool:
    host = (urlparse(url or "").netloc or "").lower()
    host = host[4:] if host.startswith("www.") else host
    includes = [d.lower().removeprefix("www.") for d in include_domains or [] if d]
    excludes = [d.lower().removeprefix("www.") for d in exclude_domains or [] if d]
    if includes and not any(host == d or host.endswith("." + d) for d in includes):
        return False
    if excludes and any(host == d or host.endswith("." + d) for d in excludes):
        return False
    return True
