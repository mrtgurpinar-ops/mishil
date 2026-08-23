"""
Mışıl Baby — Mışıl Dadı AI Chat API Endpoint
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from app.services.ai_sleep_coach import ask_mishil_dadi

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")


class CoachChatRequest(BaseModel):
    baby_name: str = Field(default="Mina", description="Bebeğin adı")
    birth_date: str = Field(default="2026-04-11", description="Bebeğin doğum tarihi (YYYY-MM-DD)")
    message: str = Field(..., min_length=1, description="Ebeveynin Mışıl Dadı'ya sorusu")
    chat_history: Optional[List[Dict[str, str]]] = Field(default=[], description="Önceki sohbet geçmişi")


class CoachChatResponse(BaseModel):
    reply: str
    tier_used: str
    baby_name: str
    timestamp: str


@router.post("/chat", response_model=CoachChatResponse, summary="Mışıl Dadı AI Pediatrik Danışmanına Soru Sor")
async def chat_with_coach(payload: CoachChatRequest):
    """
    4 Katmanlı Gemini LLM Destekli Mışıl Dadı Servisi:
    Bebeğin adına, tam ayına ve uykusuna özel şefkatli ve bilimsel çözümler sunar.
    """
    try:
        result = ask_mishil_dadi(
            baby_name=payload.baby_name,
            birth_date=payload.birth_date,
            message=payload.message,
            chat_history=payload.chat_history
        )
        return CoachChatResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mışıl Dadı yanıt üretirken bir hata oluştu: {str(e)}"
        )
