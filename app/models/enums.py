from enum import Enum


class CryType(str, Enum):
    HUNGRY = "hungry"
    TIRED = "tired"
    PAIN_COLIC = "pain_colic"
    DISCOMFORT = "discomfort"
    BURPING_NEEDED = "burping_needed"
    OVERSTIMULATED = "overstimulated"


class SoundType(str, Enum):
    # 1. Lullabies (8)
    BRAHMS_LULLABY = "brahms_lullaby"
    MOONLIGHT_LULLABY = "moonlight_lullaby"
    MOZART_432HZ = "mozart_432hz"
    MUSIC_BOX_CELESTA = "music_box_celesta"
    VELVET_GUITAR = "velvet_guitar"
    CLAIR_DE_LUNE_PIANO = "clair_de_lune_piano"
    HARP_LULLABY = "harp_lullaby"
    WARM_KALIMBA = "warm_kalimba"
    # 2. Womb & Heartbeat (7)
    DEEP_HEARTBEAT = "deep_heartbeat"
    WOMB_AMNIOTIC = "womb_amniotic"
    PLACENTA_FLOW = "placenta_flow"
    CALM_BREATH = "calm_breath"
    MATERNAL_HUMMING = "maternal_humming"
    UMBILICAL_WHOOSH = "umbilical_whoosh"
    CAR_RIDE_WOMB = "car_ride_womb"
    # 3. Noise & Shush (8)
    SHUSH_5S = "shush_5s"
    PINK_432HZ = "pink_432hz"
    BROWN_NOISE_COLIC = "brown_noise_colic"
    HAIRDRYER_CALM = "hairdryer_calm"
    FAN_DRONE = "fan_drone"
    PURE_WHITE_NOISE = "pure_white_noise"
    VACUUM_COLIC = "vacuum_colic"
    WASHING_MACHINE = "washing_machine"
    # 4. Nature & Ambience (7)
    FOREST_STREAM = "forest_stream"
    SOFT_RAIN = "soft_rain"
    OCEAN_CALM = "ocean_calm"
    NIGHT_CRICKETS = "night_crickets"
    DISTANT_THUNDER_RAIN = "distant_thunder_rain"
    WIND_LEAVES = "wind_leaves"
    CAMPFIRE_WARMTH = "campfire_warmth"
    # Legacy aliases for backward compatibility
    PINK_NOISE_432HZ = "pink_432hz"
    WHITE_NOISE = "pure_white_noise"
    BROWN_NOISE = "brown_noise_colic"
    WOMB_SOUNDS = "womb_amniotic"
    RAIN_GENTLE = "soft_rain"
    SHUSHING_RHYTHMIC = "shush_5s"
    HEARTBEAT_CALM = "deep_heartbeat"


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
