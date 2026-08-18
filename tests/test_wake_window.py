from datetime import datetime, timezone, timedelta
import pytest
from app.services.wake_window import WakeWindowService
from app.models.schemas import WakeWindowCalculateRequest


def test_wake_window_exact_age_brackets():
    """Verify age bracket wake window lookup including edge cases (exact 2.0, 12.0, 36.0 months)."""
    # 0.5 month (0-1 bracket) -> 45 min
    w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(0.5)
    assert w == 45
    assert naps == 5

    # Exactly 1.0 month -> 60 min
    w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(1.0)
    assert w == 60
    assert naps == 4

    # Exactly 2.0 months (2-4 bracket boundary) -> 90 min
    w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(2.0)
    assert w == 90
    assert naps == 4

    # Exactly 6.0 months (6-9 bracket boundary) -> 150 min
    w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(6.0)
    assert w == 150
    assert total_s == 14.0
    assert naps == 3

    # Exactly 12.0 months (12-18 bracket boundary) -> 210 min
    w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(12.0)
    assert w == 210
    assert naps == 2

    # Exactly 36.0 months (upper bound) -> 240 min
    w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(36.0)
    assert w == 240
    assert naps == 1


def test_wake_window_calculation_standard():
    """Test full wake window calculation without overtired condition."""
    now = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
    req = WakeWindowCalculateRequest(
        baby_age_months=6.5,
        last_wake_time=now,
        previous_nap_duration_minutes=60,
        daily_naps_completed=1,
    )
    res = WakeWindowService.calculate(req)

    assert res.base_wake_window_minutes == 150
    assert res.adjusted_wake_window_minutes == 150
    assert res.is_overtired_risk is False
    assert res.next_sleep_time == now + timedelta(minutes=150)
    assert res.notification_time == res.next_sleep_time - timedelta(minutes=15)
    assert res.recommended_daily_nap_count == 3
    # 3 total - 1 completed = 2 remaining
    assert len(res.remaining_naps_plan) == 2


def test_wake_window_overtired_reduction():
    """Test 15% reduction when previous nap is short (<30 min)."""
    now = datetime(2026, 8, 18, 14, 0, 0, tzinfo=timezone.utc)
    req = WakeWindowCalculateRequest(
        baby_age_months=4.0,  # base 120 min
        last_wake_time=now,
        previous_nap_duration_minutes=25,  # Short nap!
        daily_naps_completed=2,
    )
    res = WakeWindowService.calculate(req)

    assert res.base_wake_window_minutes == 120
    # 120 * 0.85 = 102 minutes
    assert res.adjusted_wake_window_minutes == 102
    assert res.is_overtired_risk is True
    assert "aşırı yorgunluk" in res.overtired_explanation.lower()
    assert res.next_sleep_time == now + timedelta(minutes=102)
    assert res.notification_time == res.next_sleep_time - timedelta(minutes=15)
