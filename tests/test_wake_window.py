# -*- coding: utf-8 -*-
import unittest
from datetime import datetime, timezone, timedelta
from app.services.wake_window import WakeWindowService
from app.models.schemas import WakeWindowCalculateRequest


class TestWakeWindowService(unittest.TestCase):
    def test_wake_window_exact_age_brackets(self):
        """Verify age bracket wake window lookup including edge cases."""
        w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(0.5)
        self.assertEqual(w, 45)
        self.assertEqual(naps, 5)

        w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(1.0)
        self.assertEqual(w, 60)
        self.assertEqual(naps, 4)

        w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(2.0)
        self.assertEqual(w, 90)
        self.assertEqual(naps, 4)

        w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(6.0)
        self.assertEqual(w, 150)
        self.assertEqual(total_s, 14.0)
        self.assertEqual(naps, 3)

        w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(12.0)
        self.assertEqual(w, 210)
        self.assertEqual(naps, 2)

        w, total_s, naps, _ = WakeWindowService.get_age_bracket_info(36.0)
        self.assertEqual(w, 240)
        self.assertEqual(naps, 1)

    def test_wake_window_calculation_standard(self):
        """Test full wake window calculation without overtired condition."""
        now = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
        req = WakeWindowCalculateRequest(
            baby_age_months=6.5,
            last_wake_time=now,
            previous_nap_duration_minutes=60,
            daily_naps_completed=1,
        )
        res = WakeWindowService.calculate(req)

        self.assertEqual(res.base_wake_window_minutes, 150)
        self.assertEqual(res.adjusted_wake_window_minutes, 150)
        self.assertFalse(res.is_overtired_risk)
        self.assertEqual(res.next_sleep_time, now + timedelta(minutes=150))
        self.assertEqual(res.notification_time, res.next_sleep_time - timedelta(minutes=15))
        self.assertEqual(res.recommended_daily_nap_count, 3)
        self.assertEqual(len(res.remaining_naps_plan), 2)

    def test_wake_window_overtired_reduction(self):
        """Test 15% reduction when previous nap is short (<30 min)."""
        now = datetime(2026, 8, 18, 14, 0, 0, tzinfo=timezone.utc)
        req = WakeWindowCalculateRequest(
            baby_age_months=4.0,
            last_wake_time=now,
            previous_nap_duration_minutes=25,
            daily_naps_completed=2,
        )
        res = WakeWindowService.calculate(req)

        self.assertEqual(res.base_wake_window_minutes, 120)
        self.assertEqual(res.adjusted_wake_window_minutes, 102)
        self.assertTrue(res.is_overtired_risk)
        self.assertIn("aşırı yorgunluk", res.overtired_explanation.lower())
        self.assertEqual(res.next_sleep_time, now + timedelta(minutes=102))
        self.assertEqual(res.notification_time, res.next_sleep_time - timedelta(minutes=15))


if __name__ == "__main__":
    unittest.main()
