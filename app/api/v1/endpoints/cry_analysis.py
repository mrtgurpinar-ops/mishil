from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.db.base import get_db
from app.db.models import User, Baby, CryEvent
from app.models.schemas import CryAnalysisResponse
from app.services.cry_analysis import CryAnalysisService
from .auth import get_current_user

router = APIRouter(prefix="/cry-analysis", tags=["Cry Audio Analysis"])


@router.post("/analyze", response_model=CryAnalysisResponse)
async def analyze_cry_audio(
    file: UploadFile = File(..., description="Bebek ağlama ses kaydı (WAV, M4A, MP3, maks 10MB)"),
    baby_id: Optional[int] = Form(None, description="Opsiyonel Bebek ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze baby crying audio file using Librosa acoustic feature extraction (MFCC, ZCR, Spectral Centroid)
    and output a heuristic probability distribution across causes (Hungry, Tired, Pain/Colic, Discomfort).
    """
    # Verify baby ownership if provided
    if baby_id:
        baby = db.query(Baby).filter(Baby.id == baby_id, Baby.user_id == current_user.id).first()
        if not baby:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Belirtilen bebek kaydı bulunamadı veya bu hesaba ait değil."
            )

    # Perform analysis
    analysis_result = await CryAnalysisService.analyze_audio(file)

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
