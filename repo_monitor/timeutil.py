"""Tidshantering och svensk datumformattering."""

from __future__ import annotations

from datetime import datetime, timezone

try:  # zoneinfo kräver tzdata; fall tillbaka till UTC om den saknas.
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("Europe/Stockholm")
    LOCAL_TZ_LABEL = "svensk tid"
except Exception:  # pragma: no cover - beror på systemet
    LOCAL_TZ = timezone.utc
    LOCAL_TZ_LABEL = "UTC"

MONTHS_SV = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]


def parse_iso(value) -> datetime | None:
    """Tolkar ISO 8601 (t.ex. '2026-11-24T10:00:00Z'). Returnerar None vid fel."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def fmt_date(value) -> str:
    """'24 november 2026'."""
    dt = value if isinstance(value, datetime) else parse_iso(value)
    if dt is None:
        return "okänt datum"
    local = dt.astimezone(LOCAL_TZ)
    return f"{local.day} {MONTHS_SV[local.month - 1]} {local.year}"


def fmt_datetime(value) -> str:
    """'24 november 2026 kl. 14:05'."""
    dt = value if isinstance(value, datetime) else parse_iso(value)
    if dt is None:
        return "okänd tidpunkt"
    local = dt.astimezone(LOCAL_TZ)
    return f"{fmt_date(dt)} kl. {local.strftime('%H:%M')}"
