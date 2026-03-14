import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from bot.scheduler_math import (
    get_next_scheduled_time, is_monthly_cooldown_active,
    days_until_cooldown_expires, local_to_utc, utc_to_local,
)


class TestGetNextScheduledTime:
    def test_morning_future(self):
        import pytz
        # Provide a fixed 6:00 UTC time so 8:00 MORNING is in the future
        tz = pytz.UTC
        fixed_now = tz.localize(datetime(2024, 1, 1, 6, 0, 0))
        with patch("bot.scheduler_math.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            # Allow datetime() constructor calls to pass through
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = get_next_scheduled_time("MORNING", "UTC")
            assert result.hour == 8

    def test_unknown_timezone_defaults_utc(self):
        result = get_next_scheduled_time("MORNING", "Invalid/Zone")
        assert result is not None

    def test_morning_past_schedules_tomorrow(self):
        result = get_next_scheduled_time("MORNING", "UTC")
        now = datetime.utcnow()
        assert result > now


class TestMonthlyCooldown:
    def test_active_cooldown(self):
        recent = datetime.utcnow() - timedelta(days=5)
        assert is_monthly_cooldown_active(recent, cooldown_days=21) is True

    def test_expired_cooldown(self):
        old = datetime.utcnow() - timedelta(days=25)
        assert is_monthly_cooldown_active(old, cooldown_days=21) is False

    def test_none_last_audit(self):
        assert is_monthly_cooldown_active(None) is False

    def test_days_remaining(self):
        last = datetime.utcnow() - timedelta(days=10)
        remaining = days_until_cooldown_expires(last, cooldown_days=21)
        assert remaining == 11

    def test_days_remaining_expired(self):
        last = datetime.utcnow() - timedelta(days=30)
        remaining = days_until_cooldown_expires(last, cooldown_days=21)
        assert remaining == 0


class TestTimezoneConversion:
    def test_local_to_utc(self):
        local = datetime(2024, 1, 1, 8, 0, 0)
        utc = local_to_utc(local, "Europe/Berlin")
        assert utc.hour in (6, 7)  # Berlin is UTC+1 or UTC+2

    def test_utc_to_local(self):
        utc = datetime(2024, 1, 1, 7, 0, 0)
        local = utc_to_local(utc, "Europe/Berlin")
        assert local.hour == 8
