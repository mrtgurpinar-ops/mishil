import os
import time
from collections import deque
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import Dict, Optional
from app.db.base import get_db
from app.db.models import User, Baby, CryEvent
from app.models.schemas import CryAnalysisResponse
from app.services.cry_analysis import CryAnalysisService
from .auth import get_current_user, get_optional_current_user

router = APIRouter(prefix="/cry-analysis", tags=["Cry Audio Analysis"])

_CRY_IP_BUCKETS: Dict[str, deque] = {}
_CRY_WINDOW_SEC = 600.0
_CRY_MAX_REQ_PER_WINDOW = 20


def _enforce_cry_abuse_rate_limit(request: Optional[Request], lang: str = "tr") -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") or request is None:
        return
    forwarded = request.headers.get("x-forwarded-for") or ""
    client_ip = (forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")) or "unknown"
    now = time.monotonic()
    bucket = _CRY_IP_BUCKETS.setdefault(client_ip, deque())
    while bucket and (now - bucket[0]) > _CRY_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= _CRY_MAX_REQ_PER_WINDOW:
        lang_clean = (lang or "tr").strip().lower()
        detail_msg = (
            "Anfragelimit für die Schrei-Audioanalyse erreicht. Bitte warte ein paar Minuten."
            if lang_clean.startswith("de")
            else (
                "Rate limit exceeded for cry audio analysis. Please wait a few minutes."
                if lang_clean.startswith("en")
                else "Kısa sürede çok fazla ses analizi isteği gönderildi. Lütfen birkaç dakika bekleyin."
            )
        )
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail_msg)
    bucket.append(now)


@router.post("/analyze", response_model=CryAnalysisResponse)
async def analyze_cry_audio(
    request: Request,
    file: UploadFile = File(..., description="Bebek ağlama ses kaydı (WAV, M4A, MP3, maks 10MB)"),
    baby_id: Optional[int] = Form(None, description="Opsiyonel Bebek ID"),
    lang: Optional[str] = Form("tr", description="Yanıt dili ('tr', 'en' veya 'de')"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Analyze baby crying audio file using Librosa acoustic feature extraction (MFCC, ZCR, Spectral Centroid)
    and output a heuristic probability distribution across causes (Hungry, Tired, Pain/Colic, Discomfort).
    """
    lang_clean = (lang or "tr").strip().lower()
    _enforce_cry_abuse_rate_limit(request, lang_clean)
    # Verify baby ownership if both baby_id and current_user are provided
    if baby_id and current_user:
        baby = db.query(Baby).filter(Baby.id == baby_id, Baby.user_id == current_user.id).first()
        if not baby:
            not_found_msg = (
                "Das angegebene Babyprofil wurde nicht gefunden oder gehört nicht zu diesem Konto."
                if lang_clean.startswith("de")
                else (
                    "Specified baby profile not found or does not belong to this account."
                    if lang_clean.startswith("en")
                    else "Belirtilen bebek kaydı bulunamadı veya bu hesaba ait değil."
                )
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=not_found_msg,
            )

    # Perform analysis
    analysis_result = await CryAnalysisService.analyze_audio(file, lang=lang or "tr")

    # Persist CryEvent log
    try:
        causes_data = [item.model_dump() for item in analysis_result.possible_causes]
        cry_event = CryEvent(
            baby_id=baby_id,
            audio_ref=file.filename,
            possible_causes_json=causes_data,
            dominant_cause=analysis_result.dominant_cause,
            recommended_action=analysis_result.recommended_action,
            recommended_sound_type=analysis_result.recommended_sound_type,
            confidence_note=analysis_result.confidence_note,
        )
        db.add(cry_event)
        db.commit()
    except Exception:
        db.rollback()
        # Continue to return response even if logging to DB fails

    return analysis_result
