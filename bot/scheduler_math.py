"""
Timezone-aware scheduling math.
Tier 1: Must have 100% unit test coverage.
"""
from datetime import datetime, timedelta
import pytz


def get_next_scheduled_time(
    delivery_time: str,
    timezone_name: str,
    nudge_hour: int = 8,
    reflection_hour: int = 20,
) -> datetime:
    """
    Calculate next UTC datetime for a MORNING or EVENING delivery.
    If the target time today has already passed, schedule for tomorrow.
    """
    try:
        tz = pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC

    now_local = datetime.now(tz)
    target_hour = nudge_hour if delivery_time == "MORNING" else reflection_hour

    target_local = now_local.replace(
        hour=target_hour, minute=0, second=0, microsecond=0
    )

    if target_local <= now_local:
        target_local += timedelta(days=1)

    return target_local.astimezone(pytz.UTC).replace(tzinfo=None)


def is_monthly_cooldown_active(last_audit: datetime, cooldown_days: int = 21) -> bool:
    """Check if monthly audit cooldown is still active."""
    if last_audit is None:
        return False
    elapsed = datetime.utcnow() - last_audit
    return elapsed.days < cooldown_days


def days_until_cooldown_expires(last_audit: datetime, cooldown_days: int = 21) -> int:
    """Return days remaining until cooldown expires. 0 if already expired."""
    if last_audit is None:
        return 0
    elapsed = datetime.utcnow() - last_audit
    remaining = cooldown_days - elapsed.days
    return max(0, remaining)


def local_to_utc(local_dt: datetime, timezone_name: str) -> datetime:
    """Convert naive local datetime to UTC."""
    try:
        tz = pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    localized = tz.localize(local_dt)
    return localized.astimezone(pytz.UTC).replace(tzinfo=None)


def utc_to_local(utc_dt: datetime, timezone_name: str) -> datetime:
    """Convert naive UTC datetime to local timezone."""
    try:
        tz = pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    aware_utc = pytz.UTC.localize(utc_dt)
    return aware_utc.astimezone(tz)
