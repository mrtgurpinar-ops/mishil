from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from app.services.ai_sleep_coach import ask_mishil_dadi, stream_mishil_dadi, normalize_lang
from app.core.logging import get_logger

logger = get_logger("coach_endpoint")
router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class CoachChatRequest(BaseModel):
    baby_name: Optional[str] = Field(default="Bebeğim", description="Bebeğin adı")
    birth_date: Optional[str] = Field(default="2026-04-11", description="Bebeğin doğum tarihi (YYYY-MM-DD)")
    user_role: str = Field(default="mother", description="Soruyu soran rol ('mother', 'father', 'nanny')")
    user_name: Optional[str] = Field(default=None, description="Soruyu soran ebeveynin adı")
    manual_leap: Optional[int] = Field(default=None, description="Manuel aktif edilmiş sıçrama numarası (1-10)")
    routine_rollup: Optional[Dict[str, Any]] = Field(default=None, description="Bebeğin son rutin rollup özeti (uyku, beslenme ml, bez, gece uyanma)")
    message: str = Field(..., min_length=1, max_length=4000, description="Ebeveynin/Dadının Mışıl Dadı'ya sorusu")
    chat_history: Optional[List[Dict[str, str]]] = Field(default=[], description="Önceki sohbet geçmişi")
    lang: Optional[str] = Field(default="tr", description="Yanıt dili ('tr' veya 'en')")


class CoachChatResponse(BaseModel):
    reply: str
    tier_used: str
    baby_name: str
    user_role: str
    timestamp: str


@router.post("/chat", response_model=CoachChatResponse, summary="Mışıl Dadı AI Ebeveyn Asistanına Soru Sor (JSON)")
async def chat_with_coach(payload: CoachChatRequest):
    """
    4 Katmanlı Gemini LLM Destekli Mışıl Dadı Servisi (Tek Parça JSON):
    Bebeğin adına, tam ayına, soruyu soran ebeveyn/dadı rolüne ve aktif gelişim sıçramasına özel şefkatli ve bilimsel çözümler sunar.
    """
    lang_norm = normalize_lang(payload.lang)
    default_baby_name = "My Baby" if lang_norm == "en" and (not payload.baby_name or payload.baby_name == "Bebeğim") else (payload.baby_name or "Bebeğim")
    try:
        result = ask_mishil_dadi(
            baby_name=default_baby_name,
            birth_date=payload.birth_date,
            message=payload.message,
            chat_history=payload.chat_history,
            user_role=payload.user_role,
            manual_leap=payload.manual_leap,
            routine_rollup=payload.routine_rollup,
            lang=lang_norm
        )
        return CoachChatResponse(**result)
    except Exception as e:
        logger.error(f"Coach chat error: {str(e)}", exc_info=True)
        err_msg = (
            "Mishil Nanny is experiencing high traffic right now. Please try again in a moment."
            if lang_norm == "en"
            else "Mışıl Dadı şu an yanıt üretirken geçici bir yoğunluk yaşıyor, lütfen birazdan tekrar deneyin."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=err_msg
        )


@router.post("/stream", summary="Mışıl Dadı AI Canlı Token Akışı (Server-Sent Events / SSE)")
async def stream_coach_response(payload: CoachChatRequest):
    """
    Gerçek Zamanlı Kelime Akışı (SSE Streaming):
    Kelimeleri 300ms içinde canlı canlı ekrana döker, kesintisiz ve sıfır gecikmeli danışmanlık sağlar.
    """
    lang_norm = normalize_lang(payload.lang)
    default_baby_name = "My Baby" if lang_norm == "en" and (not payload.baby_name or payload.baby_name == "Bebeğim") else (payload.baby_name or "Bebeğim")
    try:
        generator = stream_mishil_dadi(
            baby_name=default_baby_name,
            birth_date=payload.birth_date,
            message=payload.message,
            chat_history=payload.chat_history,
            user_role=payload.user_role,
            manual_leap=payload.manual_leap,
            routine_rollup=payload.routine_rollup,
            lang=lang_norm
        )
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        logger.error(f"Coach stream error: {str(e)}", exc_info=True)
        err_msg = (
            "Mishil Nanny live response stream could not be started right now. Please try again."
            if lang_norm == "en"
            else "Mışıl Dadı canlı yanıt akışı şu an başlatılamadı, lütfen tekrar deneyin."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=err_msg
        )

