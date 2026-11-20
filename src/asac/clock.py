"""Time source. ``ASAC_FIXED_TIME`` pins the clock so tests and golden files are reproducible."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta

FIXED_ENV = "ASAC_FIXED_TIME"
_DURATION = re.compile(r"^(\d+)([smhd])$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def now() -> datetime:
    fixed = os.environ.get(FIXED_ENV)
    if fixed:
        return parse_ts(fixed)
    return datetime.now(UTC)


def fmt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return fmt(now())


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def parse_duration(value: str) -> timedelta:
    m = _DURATION.match(value.strip())
    if not m:
        raise ValueError(f"invalid duration '{value}' (use e.g. 30m, 24h, 2d)")
    return timedelta(**{_UNITS[m.group(2)]: int(m.group(1))})
