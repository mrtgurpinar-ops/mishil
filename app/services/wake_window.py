from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from app.models.schemas import (
    WakeWindowCalculateRequest,
    WakeWindowResponse,
    SleepWindowPlanItem,
)
from app.models.enums import SleepType


class WakeWindowConfig:
    """
    Age bracket reference table for 0-36 months old infants.
    Format: (min_age, max_age, base_wake_window_min, total_sleep_hours, daily_nap_count, advice)
    """
    TABLE: List[Tuple[float, float, int, float, int, str]] = [
        (0.0, 1.0, 45, 16.5, 5, "Yenidoğan döneminde bebeğinizi 45 dakikadan fazla uyanık tutmamaya özen gösterin."),
        (1.0, 2.0, 60, 15.5, 4, "1-2 aylık bebekler için uyanıklık süresi 60 dakikadır. Esneme ve göz ovuşturma işaretlerine dikkat edin."),
        (2.0, 4.0, 90, 14.5, 4, "2-4 ay arası gündüz uykuları belirginleşir. 90 dakikalık pencere idealdir."),
        (4.0, 6.0, 120, 14.0, 3, "4-6 ayda 4. ay uyku gerilemesi görülebilir. 2 saatlik pencerelerle ritmi koruyun."),
        (6.0, 9.0, 150, 14.0, 3, "6-9 ayda 3 nap rutini oturur. Yaklaşık 2.5 saatlik uyanıklık idealdir."),
        (9.0, 12.0, 180, 13.5, 2, "9-12 ayda genellikle 2 nap düzenine geçilir. Uyanıklık penceresi 3 saattir."),
        (12.0, 18.0, 210, 13.0, 2, "12-18 ayda 2'den 1 nap'e geçiş dönemi başlar. 3.5 saatlik uyanıklık hedeflenir."),
        (18.0, 36.0, 240, 12.5, 1, "18-36 ayda tek öğle uykusu yeterlidir. Uyanıklık penceresi 4 saattir."),
    ]


class WakeWindowService:
    """Service to calculate dynamic wake windows and sleep budgets."""

    @classmethod
    def get_age_bracket_info(cls, age_months: float) -> Tuple[int, float, int, str]:
        """Find the matching age bracket config for given age in months."""
        clamped_age = max(0.0, min(float(age_months), 36.0))
        
        for min_age, max_age, wake_window, total_sleep, nap_count, advice in WakeWindowConfig.TABLE:
            # Handle upper inclusive bound for 36.0
            if max_age == 36.0:
                if min_age <= clamped_age <= max_age:
                    return wake_window, total_sleep, nap_count, advice
            elif min_age <= clamped_age < max_age:
                return wake_window, total_sleep, nap_count, advice
                
        # Default fallback
        return 240, 12.5, 1, "Yaşa uygun uyku rutinine devam ediniz."

    @classmethod
    def calculate(cls, payload: WakeWindowCalculateRequest) -> WakeWindowResponse:
        """
        Calculate dynamic next sleep time, overtired reduction, and remaining nap projections.
        """
        base_wake_window, total_sleep_hours, rec_nap_count, advice = cls.get_age_bracket_info(
            payload.baby_age_months
        )

        adjusted_wake_window = base_wake_window
        is_overtired = False
        overtired_exp = None

        # Check for overtired condition (< 30 minutes nap)
        if (
            payload.previous_nap_duration_minutes is not None
            and payload.previous_nap_duration_minutes < 30
        ):
            is_overtired = True
            # Shorten wake window by 15% to prevent overtired meltdown
            adjusted_wake_window = max(20, int(round(base_wake_window * 0.85)))
            overtired_exp = (
                f"Önceki uyku {payload.previous_nap_duration_minutes} dakika sürdüğü için "
                f"aşırı yorgunluk (overtired) riski tespit edildi. "
                f"Uyanıklık penceresi %15 kısaltılarak {adjusted_wake_window} dakikaya uyarlandı."
            )

        last_wake = payload.last_wake_time
        next_sleep = last_wake + timedelta(minutes=adjusted_wake_window)
        notification_time = next_sleep - timedelta(minutes=15)

        # Calculate remaining nap schedule projection
        completed_naps = payload.daily_naps_completed or 0
        remaining_naps_count = max(0, rec_nap_count - completed_naps)
        
        remaining_plan: List[SleepWindowPlanItem] = []
        current_time_cursor = next_sleep
        
        # Project subsequent nap(s)
        for i in range(1, remaining_naps_count + 1):
            nap_num = completed_naps + i
            if i == 1:
                plan_start = next_sleep
            else:
                # Next nap assumes ~60-90 min nap followed by base wake window
                plan_start = current_time_cursor
            
            # Expected nap duration (e.g. 60-90 mins)
            expected_duration = 75 if payload.baby_age_months < 12 else 90
            remaining_plan.append(
                SleepWindowPlanItem(
                    nap_number=nap_num,
                    expected_start_time=plan_start,
                    expected_duration_minutes=expected_duration,
                    sleep_type=SleepType.NAP
                )
            )
            # Advance cursor for hypothetical next nap
            current_time_cursor = plan_start + timedelta(minutes=expected_duration + base_wake_window)

        return WakeWindowResponse(
            baby_age_months=payload.baby_age_months,
            base_wake_window_minutes=base_wake_window,
            adjusted_wake_window_minutes=adjusted_wake_window,
            is_overtired_risk=is_overtired,
            overtired_explanation=overtired_exp,
            last_wake_time=last_wake,
            next_sleep_time=next_sleep,
            notification_time=notification_time,
            daily_total_sleep_hours_recommended=total_sleep_hours,
            recommended_daily_nap_count=rec_nap_count,
            remaining_naps_plan=remaining_plan,
            advice=advice,
        )
