from enum import Enum


class CryType(str, Enum):
    HUNGRY = "hungry"
    TIRED = "tired"
    PAIN_COLIC = "pain_colic"
    DISCOMFORT = "discomfort"
    BURPING_NEEDED = "burping_needed"
    OVERSTIMULATED = "overstimulated"


class SoundType(str, Enum):
    PINK_NOISE_432HZ = "pink_noise_432hz"
    WHITE_NOISE = "white_noise"
    BROWN_NOISE = "brown_noise"
    WOMB_SOUNDS = "womb_sounds"
    RAIN_GENTLE = "rain_gentle"
    SHUSHING_RHYTHMIC = "shushing_rhythmic"
    HEARTBEAT_CALM = "heartbeat_calm"
    BRAHMS_LULLABY = "brahms_lullaby"


class SubscriptionStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    GRACE_PERIOD = "grace_period"


class SubscriptionPlan(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


class SleepType(str, Enum):
    NAP = "nap"
    NIGHT = "night"


class RoutineType(str, Enum):
    FEEDING = "feeding"
    DIAPER = "diaper"
    SLEEP = "sleep"
    BATH = "bath"
    MOOD = "mood"
    TUMMY_TIME = "tummy_time"
