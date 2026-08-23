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
