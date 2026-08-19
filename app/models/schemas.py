from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
import re
from .enums import CryType, SoundType, SubscriptionStatus, SubscriptionPlan, SleepType, RoutineType


# ==========================================
# 1. Base & Generic Schemas
# ==========================================
class BaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    success: bool = True
    message: Optional[str] = None


# ==========================================
# 2. Auth & User / Baby Schemas
# ==========================================
class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6, max_length=100)
    full_name: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError("Geçerli bir e-posta adresi giriniz.")
        return v


class UserLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    email: str
    subscription_status: SubscriptionStatus


class BabyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    birth_date: datetime
    gender: Optional[str] = Field(None, pattern="^(male|female|other)$")


class BabyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    name: str
    birth_date: datetime
    age_in_months: float
    created_at: datetime


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: Optional[str] = None
    subscription_status: SubscriptionStatus
    trial_ends_at: Optional[datetime] = None
    created_at: datetime
    babies: List[BabyResponse] = []


# ==========================================
# 3. Wake Window Schemas
# ==========================================
class WakeWindowCalculateRequest(BaseModel):
    baby_age_months: float = Field(..., ge=0.0, le=36.0, description="Bebeğin ayı (0.0 - 36.0)")
    last_wake_time: datetime = Field(..., description="Bebeğin son uyanma zamanı (ISO datetime)")
    previous_nap_duration_minutes: Optional[int] = Field(
        None, ge=0, description="Bir önceki nap süresi (dakika). <30 dk ise overtired koruması tetiklenir."
    )
    daily_naps_completed: Optional[int] = Field(
        None, ge=0, description="Bugün tamamlanan nap sayısı"
    )


class SleepWindowPlanItem(BaseModel):
    nap_number: int
    expected_start_time: datetime
    expected_duration_minutes: int
    sleep_type: SleepType = SleepType.NAP


class WakeWindowResponse(BaseModel):
    baby_age_months: float
    base_wake_window_minutes: int
    adjusted_wake_window_minutes: int
    is_overtired_risk: bool
    overtired_explanation: Optional[str] = None
    last_wake_time: datetime
    next_sleep_time: datetime
    notification_time: datetime
    daily_total_sleep_hours_recommended: float
    recommended_daily_nap_count: int
    remaining_naps_plan: List[SleepWindowPlanItem] = []
    advice: str


# ==========================================
# 4. Cry Analysis Schemas
# ==========================================
class CryCauseProbability(BaseModel):
    cause: CryType
    cause_title: str
    likelihood: float = Field(..., ge=0.0, le=1.0, description="Olasılık skoru (0.0 - 1.0)")
    description: str


class CryAnalysisResponse(BaseModel):
    audio_duration_seconds: float
    possible_causes: List[CryCauseProbability]
    dominant_cause: CryType
    confidence_note: str = "Bu tahmin klinik teşhis değildir, ebeveyn için ipucu niteliğindedir."
    recommended_action: str
    recommended_sound_type: SoundType
    sound_url_mock: str
    features_extracted: Dict[str, Any]
    created_at: datetime


# ==========================================
# 5. Sounds Library Schemas
# ==========================================
class SoundItemResponse(BaseModel):
    id: str
    sound_type: SoundType
    title: str
    description: str
    duration_seconds: int
    category: str
    frequency_hz: Optional[int] = None
    stream_url: str
    is_premium: bool = False


class SoundListResponse(BaseModel):
    total: int
    categories: List[str]
    sounds: List[SoundItemResponse]


# ==========================================
# 6. Routines & Logs Schemas
# ==========================================
class RoutineLogCreateRequest(BaseModel):
    baby_id: int
    routine_type: RoutineType
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    details: Dict[str, Any] = Field(default_factory=dict, description="Ek veriler (ml, sol/sağ meme, bez tipi vb.)")
    notes: Optional[str] = None


class RoutineLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    baby_id: int
    routine_type: RoutineType
    start_time: datetime
    end_time: Optional[datetime] = None
    details: Dict[str, Any]
    notes: Optional[str] = None
    created_at: datetime


# ==========================================
# 7. Subscription & RevenueCat Schemas
# ==========================================
class StartTrialRequest(BaseModel):
    baby_id: Optional[int] = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    status: SubscriptionStatus
    plan: Optional[SubscriptionPlan] = None
    trial_ends_at: Optional[datetime] = None
    is_active: bool
    days_left_in_trial: Optional[int] = None


class RevenueCatWebhookEvent(BaseModel):
    api_version: Optional[str] = "1.0"
    event: Dict[str, Any]
