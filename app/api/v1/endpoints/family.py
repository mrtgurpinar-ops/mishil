"""
Mışıl Baby — Family, Nanny & Co-Parenting Cloud Sync API Endpoints
"""
import random
import string
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

router = APIRouter()

# In-memory fast persistent fallback store (and sync bridge)
FAMILY_STORE: Dict[str, Dict[str, Any]] = {
    "MSL782": {
        "id": 1,
        "name": "Mina'nın Ailesi",
        "invite_code": "MSL782",
        "members": [
            {"id": 1, "role": "mother", "name": "Zeynep (Anne)", "joined_at": "2026-08-20T10:00:00Z"},
            {"id": 2, "role": "father", "name": "Emre (Baba)", "joined_at": "2026-08-21T14:30:00Z"},
            {"id": 3, "role": "nanny", "name": "Ayşe Hanım (Gündüz Dadısı)", "joined_at": "2026-08-22T08:15:00Z"}
        ],
        "baby": {
            "name": "Mina",
            "birth_date": "2026-04-11",
            "gender": "female",
            "development_score": 84,
            "manual_leap": None,
            "is_early_leap_active": False
        },
        "created_at": datetime.now(timezone.utc).isoformat()
    }
}


def _gen_code() -> str:
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "MSL" + "".join(random.choices(chars, k=3))


class FamilyCreateRequest(BaseModel):
    family_name: str = Field(default="Mina'nın Ailesi", description="Aile Grubu Adı")
    creator_role: str = Field(default="mother", description="Oluşturan kişinin rolü ('mother', 'father', 'nanny')")
    creator_name: str = Field(default="Anne", description="Oluşturan kişinin adı")
    baby_name: str = Field(default="Mina", description="Bebek adı")
    birth_date: str = Field(default="2026-04-11", description="Doğum tarihi (YYYY-MM-DD)")


class FamilyJoinRequest(BaseModel):
    invite_code: str = Field(..., min_length=4, max_length=10, description="6 Haneli Aile Kodu (Örn: MSL782)")
    role: str = Field(default="nanny", description="Katılan kişinin rolü ('mother', 'father', 'nanny', 'grandparent')")
    name: str = Field(default="Dadı / Bakıcı", description="Kişinin görünen adı")


class LeapOverrideRequest(BaseModel):
    invite_code: str = Field(..., description="Aile Kodu")
    leap_number: Optional[int] = Field(None, description="Manuel aktif edilecek sıçrama numarası (1-10) veya None (otomatik takvime dönüş)")
    is_active: bool = Field(True, description="Erken atak aktif mi?")


@router.post("/create", summary="Yeni Aile & Dadı Paylaşım Grubu Oluştur")
async def create_family(payload: FamilyCreateRequest):
    code = _gen_code()
    while code in FAMILY_STORE:
        code = _gen_code()

    fam = {
        "id": len(FAMILY_STORE) + 1,
        "name": payload.family_name,
        "invite_code": code,
        "members": [
            {"id": 1, "role": payload.creator_role, "name": payload.creator_name, "joined_at": datetime.now(timezone.utc).isoformat()}
        ],
        "baby": {
            "name": payload.baby_name,
            "birth_date": payload.birth_date,
            "gender": "female",
            "development_score": 84,
            "manual_leap": None,
            "is_early_leap_active": False
        },
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    FAMILY_STORE[code] = fam

    return {
        "success": True,
        "message": f"Aile grubu başarıyla oluşturuldu. Davet Kodu: {code}",
        "invite_code": code,
        "family": fam
    }


@router.post("/join", summary="Aile Davet Kodu ile Aileye Katıl (Baba/Dadı)")
async def join_family(payload: FamilyJoinRequest):
    code = payload.invite_code.strip().upper()
    if code not in FAMILY_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"'{code}' kodlu aile grubu bulunamadı. Lütfen kodu kontrol ediniz.")

    fam = FAMILY_STORE[code]
    new_member = {
        "id": len(fam["members"]) + 1,
        "role": payload.role,
        "name": payload.name,
        "joined_at": datetime.now(timezone.utc).isoformat()
    }
    fam["members"].append(new_member)

    return {
        "success": True,
        "message": f"{payload.name} ({payload.role}) başarıyla {fam['name']} grubuna katıldı!",
        "family": fam
    }


@router.get("/sync/{invite_code}", summary="Canlı Aile & Bebek Gelişim Verisi Senkronizasyonu")
async def sync_family(invite_code: str):
    code = invite_code.strip().upper()
    if code not in FAMILY_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aile grubu bulunamadı.")

    return {
        "success": True,
        "family": FAMILY_STORE[code]
    }


@router.post("/leap-override", summary="Manuel Erken Atak Başlat / Otomatik Takvime Dön")
async def set_leap_override(payload: LeapOverrideRequest):
    code = payload.invite_code.strip().upper()
    if code not in FAMILY_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aile grubu bulunamadı.")

    fam = FAMILY_STORE[code]
    fam["baby"]["manual_leap"] = payload.leap_number if payload.is_active else None
    fam["baby"]["is_early_leap_active"] = payload.is_active

    status_msg = f"{payload.leap_number}. Sıçrama Erken Atak olarak manuel başlatıldı!" if payload.is_active else "Otomatik Wonder Weeks takvimine geri dönüldü."

    return {
        "success": True,
        "message": status_msg,
        "baby": fam["baby"]
    }
