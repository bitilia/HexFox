"""Small formatting helpers shared by the UI."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw
    return raw


def short_host(url: str) -> str:
    try:
        host = urlparse(url).netloc or url
        return host.replace("www.", "")
    except Exception:
        return url


def format_seconds(value) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}s" if value >= 1 else f"{value * 1000:.0f}ms"


def format_bytes(value) -> str:
    if value is None:
        return "—"
    value = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"
