from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.core.logging import get_logger

logger = get_logger("notification")


class PushNotificationService:
    """
    Push notification abstraction for mobile platforms (FCM / APNs).
    Dispatches wake window alerts 15 minutes before the next expected sleep time.
    """

    @classmethod
    async def send_wake_window_reminder(
        cls,
        user_id: int,
        baby_name: str,
        sleep_time: datetime,
        notification_time: datetime,
        device_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Schedule or dispatch 15-min pre-sleep reminder.
        Example: "Bebeğiniz Melis için uyku vakti yaklaşıyor (15 dk kaldı). Odayı karartıp sakinleştirici ses açabilirsiniz."
        """
        message_title = f"🌙 {baby_name} için Uyku Vakti Yaklaşıyor!"
        message_body = (
            f"Bebeğinizin bir sonraki uyku saati: {sleep_time.strftime('%H:%M')}. "
            "Aşırı yorgunluğu önlemek için ortamı loşlaştırıp pışpışlama sesini başlatabilirsiniz."
        )

        logger.info(
            f"Dispatched Wake Window Push Notification to user={user_id}, "
            f"baby={baby_name}, target_time={notification_time.isoformat()}"
        )

        # In production, integrate Firebase Admin SDK (messaging.send) or OneSignal / APNs HTTP/2
        return {
            "status": "queued",
            "user_id": user_id,
            "baby_name": baby_name,
            "title": message_title,
            "body": message_body,
            "scheduled_for": notification_time.isoformat(),
            "channel": "fcm_sleep_reminders",
        }
