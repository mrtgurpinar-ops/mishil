from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    security_bearer,
)
from app.core.config import settings
from app.db.base import get_db
from app.db.models import User, Baby, Subscription
from app.models.enums import SubscriptionStatus
from app.models.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserProfileResponse,
    BabyCreateRequest,
    BabyResponse,
    BaseResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Profile"])


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Dependency to retrieve and validate authenticated user from Bearer JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik doğrulama başlığı (Authorization: Bearer <token>) eksik.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kimlik tokeni (subject eksik).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.id == int(user_id_str)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı bulunamadı veya hesabı devre dışı bırakılmış.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account and return JWT access token."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi ile kayıtlı bir hesap zaten mevcut."
        )

    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        subscription_status=SubscriptionStatus.TRIAL,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"email": user.email}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        email=user.email,
        subscription_status=user.subscription_status,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email and password to receive JWT access token."""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz e-posta veya şifre."
        )

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"email": user.email}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        email=user.email,
        subscription_status=user.subscription_status,
    )


@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieve currently authenticated user's profile and registered babies."""
    babies = db.query(Baby).filter(Baby.user_id == current_user.id).all()
    
    baby_responses = [
        BabyResponse(
            id=b.id,
            user_id=b.user_id,
            name=b.name,
            birth_date=b.birth_date,
            age_in_months=b.age_in_months,
            created_at=b.created_at,
        )
        for b in babies
    ]

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        subscription_status=current_user.subscription_status,
        trial_ends_at=current_user.trial_ends_at,
        created_at=current_user.created_at,
        babies=baby_responses,
    )


@router.post("/babies", response_model=BabyResponse, status_code=status.HTTP_201_CREATED)
def create_baby(
    payload: BabyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a baby profile to current user account."""
    baby = Baby(
        user_id=current_user.id,
        name=payload.name,
        birth_date=payload.birth_date,
        gender=payload.gender,
    )
    db.add(baby)
    db.commit()
    db.refresh(baby)

    return BabyResponse(
        id=baby.id,
        user_id=baby.user_id,
        name=baby.name,
        birth_date=baby.birth_date,
        age_in_months=baby.age_in_months,
        created_at=baby.created_at,
    )
