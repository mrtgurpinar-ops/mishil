from datetime import datetime, timezone
import random
import string
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Float,
    JSON,
    Boolean,
    Enum as SQLEnum,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .base import Base
from app.models.enums import (
    CryType,
    SoundType,
    SubscriptionStatus,
    SubscriptionPlan,
    SleepType,
    RoutineType,
)


def generate_family_code() -> str:
    """Generate 6-character unique alphanumeric family sync code (e.g., MSL849)."""
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "MSL" + "".join(random.choices(chars, k=3))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    subscription_status = Column(
        SQLEnum(SubscriptionStatus),
        default=SubscriptionStatus.TRIAL,
        nullable=False,
    )
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    babies = relationship("Baby", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    family_memberships = relationship("FamilyMember", back_populates="user", cascade="all, delete-orphan")


class FamilyGroup(Base):
    __tablename__ = "family_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, default="Mışıl Ailem")
    invite_code = Column(String(20), unique=True, index=True, default=generate_family_code, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    members = relationship("FamilyMember", back_populates="family", cascade="all, delete-orphan")
    babies = relationship("Baby", back_populates="family", cascade="all, delete-orphan")


class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("family_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), default="mother", nullable=False)  # 'mother', 'father', 'nanny', 'grandparent'
    nickname = Column(String(100), nullable=True)
    can_edit = Column(Boolean, default=True)
    joined_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    family = relationship("FamilyGroup", back_populates="members")
    user = relationship("User", back_populates="family_memberships")


class Baby(Base):
    __tablename__ = "babies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id = Column(Integer, ForeignKey("family_groups.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False)
    birth_date = Column(DateTime(timezone=True), nullable=False)
    gender = Column(String(20), nullable=True)
    development_score = Column(Integer, default=84)
    manual_active_leap = Column(Integer, nullable=True)  # Ebeveynin erken başlattığı sıçrama ID'si
    is_early_leap_active = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="babies")
    family = relationship("FamilyGroup", back_populates="babies")
    sleep_logs = relationship("SleepLog", back_populates="baby", cascade="all, delete-orphan")
    cry_events = relationship("CryEvent", back_populates="baby", cascade="all, delete-orphan")
    routine_logs = relationship("RoutineLog", back_populates="baby", cascade="all, delete-orphan")
    dadi_chats = relationship("DadiChatHistory", back_populates="baby", cascade="all, delete-orphan")
    development_logs = relationship("DevelopmentLog", back_populates="baby", cascade="all, delete-orphan")

    @property
    def age_in_months(self) -> float:
        now = datetime.now(timezone.utc)
        bdate = self.birth_date
        if bdate.tzinfo is None:
            bdate = bdate.replace(tzinfo=timezone.utc)
        days = (now - bdate).days
        return max(0.0, round(days / 30.4375, 1))

    @property
    def age_in_weeks(self) -> int:
        now = datetime.now(timezone.utc)
        bdate = self.birth_date
        if bdate.tzinfo is None:
            bdate = bdate.replace(tzinfo=timezone.utc)
        days = (now - bdate).days
        return max(0, int(days / 7))


class DadiChatHistory(Base):
    __tablename__ = "dadi_chat_history"

    id = Column(Integer, primary_key=True, index=True)
    baby_id = Column(Integer, ForeignKey("babies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_role = Column(String(50), default="mother", nullable=False)  # 'mother', 'father', 'nanny'
    message = Column(Text, nullable=False)
    reply = Column(Text, nullable=False)
    tier_used = Column(String(100), default="Gemini 3.5 Flash")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    baby = relationship("Baby", back_populates="dadi_chats")


class DevelopmentLog(Base):
    __tablename__ = "development_logs"

    id = Column(Integer, primary_key=True, index=True)
    baby_id = Column(Integer, ForeignKey("babies.id", ondelete="CASCADE"), nullable=False)
    leap_number = Column(Integer, nullable=False)
    is_early_override = Column(Boolean, default=False)
    status = Column(String(50), default="active")  # 'completed', 'active', 'upcoming'
    notes = Column(Text, nullable=True)
    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    baby = relationship("Baby", back_populates="development_logs")


class SleepLog(Base):
    __tablename__ = "sleep_logs"

    id = Column(Integer, primary_key=True, index=True)
    baby_id = Column(Integer, ForeignKey("babies.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    sleep_type = Column(SQLEnum(SleepType), default=SleepType.NAP, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    baby = relationship("Baby", back_populates="sleep_logs")


class CryEvent(Base):
    __tablename__ = "cry_events"

    id = Column(Integer, primary_key=True, index=True)
    baby_id = Column(Integer, ForeignKey("babies.id", ondelete="CASCADE"), nullable=True)
    audio_ref = Column(String(255), nullable=True)
    possible_causes_json = Column(JSON, nullable=False)
    dominant_cause = Column(SQLEnum(CryType), nullable=False)
    recommended_action = Column(Text, nullable=True)
    recommended_sound_type = Column(SQLEnum(SoundType), nullable=True)
    confidence_note = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    baby = relationship("Baby", back_populates="cry_events")


class RoutineLog(Base):
    __tablename__ = "routine_logs"

    id = Column(Integer, primary_key=True, index=True)
    baby_id = Column(Integer, ForeignKey("babies.id", ondelete="CASCADE"), nullable=False)
    routine_type = Column(SQLEnum(RoutineType), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    details_json = Column(JSON, default=dict, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    baby = relationship("Baby", back_populates="routine_logs")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan = Column(SQLEnum(SubscriptionPlan), default=SubscriptionPlan.YEARLY, nullable=True)
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.TRIAL, nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    provider_ref = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="subscriptions")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(Text, nullable=False)
    sentiment = Column(String(50), default="needs_improvement", nullable=False)  # "still_awake", "needs_improvement", "feature_request"
    baby_age_months = Column(Integer, nullable=True)
    contact_info = Column(String(255), nullable=True)
    platform = Column(String(50), default="ios", nullable=True)  # "ios", "android", "web"
    app_version = Column(String(50), nullable=True)
    ip_address = Column(String(100), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class BridgeClick(Base):
    __tablename__ = "bridge_clicks"

    id = Column(Integer, primary_key=True, index=True)
    route_path = Column(String(64), index=True, nullable=False)  # '/ios', '/download', '/android', etc.
    channel = Column(String(50), index=True, nullable=False)  # 'meta_ads', 'instagram_bio', 'google_play_direct', 'landing'
    os_family = Column(String(32), index=True, nullable=False)  # 'ios', 'android', 'desktop', 'bot'
    device_detail = Column(String(100), nullable=True)  # 'iPhone', 'Android Phone', 'Meta Crawler', etc.
    app_webview = Column(String(64), index=True, nullable=True)  # 'Instagram App', 'Facebook App', 'WhatsApp', 'Safari/Chrome'
    target_store = Column(String(32), nullable=True)  # 'app_store', 'google_play', 'landing_bot'
    is_bot = Column(Boolean, default=False, index=True, nullable=False)
    is_unique = Column(Boolean, default=True, index=True, nullable=False)
    has_fbclid = Column(Boolean, default=False, nullable=False)
    fbclid = Column(String(255), nullable=True)
    utm_source = Column(String(100), nullable=True)
    utm_campaign = Column(String(100), nullable=True)
    referrer = Column(String(255), nullable=True)
    country = Column(String(16), nullable=True)
    ip_masked = Column(String(64), index=True, nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )


class AppInstallSignal(Base):
    __tablename__ = "app_install_signals"

    id = Column(Integer, primary_key=True, index=True)
    device_uid = Column(String(128), index=True, nullable=False)
    event_type = Column(String(50), index=True, nullable=False, default="first_open")  # 'first_open', 'store_jump', 'baby_created', 'cry_analyzed'
    os_family = Column(String(32), index=True, nullable=False)  # 'ios', 'android', 'desktop'
    platform = Column(String(50), nullable=True)  # 'ios_native', 'android_native', 'web_pwa'
    app_version = Column(String(32), nullable=True)
    ip_masked = Column(String(64), index=True, nullable=True)
    country = Column(String(16), nullable=True)
    matched_click_id = Column(Integer, nullable=True, index=True)
    matched_channel = Column(String(50), index=True, nullable=True)  # 'meta_ads', 'instagram_bio', 'organic_or_asa'
    match_confidence = Column(String(32), index=True, nullable=False, default="unmatched")  # 'high', 'medium', 'unmatched'
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )


class CampaignConfig(Base):
    __tablename__ = "campaign_configs"

    id = Column(Integer, primary_key=True, index=True)
    channel_key = Column(String(64), unique=True, index=True, nullable=False)  # 'apple_search_ads', 'meta_ads', 'instagram_bio', 'google_play_organic'
    display_name = Column(String(100), nullable=False)
    spend_usd = Column(Float, default=0.0, nullable=False)
    cpt_bid_usd = Column(Float, default=0.0, nullable=False)
    reported_impressions = Column(Integer, default=0, nullable=False)
    reported_clicks = Column(Integer, default=0, nullable=False)
    reported_installs = Column(Integer, default=0, nullable=False)
    store_rating = Column(Float, default=5.0, nullable=False)
    store_reviews_count = Column(Integer, default=5, nullable=False)
    notes = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class StoreDailyMetric(Base):
    """Apple App Store Connect ve Google Play günlük resmi metrik ambarı."""
    __tablename__ = "store_daily_metrics"
    __table_args__ = (
        UniqueConstraint("metric_date", "platform", name="uq_store_daily_metric_date_platform"),
    )

    id = Column(Integer, primary_key=True, index=True)
    metric_date = Column(String(16), index=True, nullable=False)  # 'YYYY-MM-DD'
    platform = Column(String(32), index=True, nullable=False, default="ios")  # 'ios' | 'android'
    impressions = Column(Integer, default=0, nullable=False)
    impressions_unique = Column(Integer, default=0, nullable=False)
    page_views = Column(Integer, default=0, nullable=False)
    page_views_unique = Column(Integer, default=0, nullable=False)
    downloads_total = Column(Integer, default=0, nullable=False)
    downloads_search = Column(Integer, default=0, nullable=False)
    downloads_browse = Column(Integer, default=0, nullable=False)
    downloads_referrer = Column(Integer, default=0, nullable=False)
    redownloads = Column(Integer, default=0, nullable=False)
    active_sessions = Column(Integer, default=0, nullable=False)
    active_paid_subs = Column(Integer, default=0, nullable=False)
    active_free_trials = Column(Integer, default=0, nullable=False)
    active_offer_code_subs = Column(Integer, default=0, nullable=False)
    gross_revenue_try = Column(Float, default=0.0, nullable=False)
    net_proceeds_try = Column(Float, default=0.0, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SubscriberLedger(Base):
    """Apple SUBSCRIBER (1_3) ve Google Play subscriptionsv2 tekil abone yaşam döngüsü defteri."""
    __tablename__ = "subscriber_ledger"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(String(128), unique=True, index=True, nullable=False)  # Apple Subscriber ID veya Google Token Hash
    platform = Column(String(32), index=True, nullable=False, default="ios")
    product_id = Column(String(64), index=True, nullable=False)  # 'misil_monthly', 'misil_annual'
    plan_label = Column(String(100), nullable=False)  # 'Aylık Esnek', 'Yıllık VIP'
    status = Column(String(64), index=True, nullable=False)  # 'paid_active', 'offer_code_trial', 'intro_free_trial', 'cancelled'
    offer_type = Column(String(64), nullable=False)  # 'standard_paid', 'offer_code', 'intro_7d_trial'
    offer_code_name = Column(String(100), nullable=True)  # Örn: 'DamlaEge2026'
    started_date = Column(String(16), index=True, nullable=False)  # 'YYYY-MM-DD'
    converted_or_renewed_date = Column(String(16), nullable=True)  # 'YYYY-MM-DD'
    maturity_or_renewal_date = Column(String(16), index=True, nullable=False)  # Tahsilat / Vade Günü 'YYYY-MM-DD'
    auto_renew_enabled = Column(Boolean, default=True, nullable=False)
    customer_price_try = Column(Float, default=0.0, nullable=False)
    developer_proceeds_try = Column(Float, default=0.0, nullable=False)
    expected_next_price_try = Column(Float, default=0.0, nullable=False)
    expected_next_proceeds_try = Column(Float, default=0.0, nullable=False)
    country = Column(String(16), default="TR", nullable=False)
    device_type = Column(String(64), default="iPhone", nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SubscriptionLifecycleEvent(Base):
    """Apple SUBSCRIPTION_EVENT (1_3) abonelik olay günlüğü (Start, Paid Conversion, Cancel, Reactivate)."""
    __tablename__ = "subscription_lifecycle_events"

    id = Column(Integer, primary_key=True, index=True)
    event_date = Column(String(16), index=True, nullable=False)
    platform = Column(String(32), default="ios", nullable=False)
    event_type = Column(String(128), index=True, nullable=False)
    product_id = Column(String(64), nullable=False)
    plan_label = Column(String(100), nullable=True)
    offer_code_name = Column(String(100), nullable=True)
    country = Column(String(16), default="TR", nullable=False)
    device_type = Column(String(64), default="iPhone", nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    days_before_canceling = Column(String(32), nullable=True)
    cancellation_reason = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class StoreSyncState(Base):
    """Apple & Google mağaza API senkronizasyon durumu ve kalıcı JSON önbelleği."""
    __tablename__ = "store_sync_states"

    id = Column(Integer, primary_key=True, index=True)
    state_key = Column(String(64), unique=True, index=True, nullable=False, default="primary_store_baseline")
    snapshot_json = Column(JSON, nullable=False, default=dict)
    last_synced_at_str = Column(String(64), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )



