from typing import List, Optional
from fastapi import APIRouter, Query, Depends
from app.core.config import settings
from app.models.enums import SoundType
from app.models.schemas import SoundListResponse, SoundItemResponse
from app.db.models import User
from .auth import get_current_user

router = APIRouter(prefix="/sounds", tags=["Soothing Sleep & Routine Sounds"])


def _sound_url(filename: str) -> str:
    """Build sound streaming URL. Uses SOUNDS_BASE_URL from config if set (CDN), else local /sounds mount."""
    base = settings.SOUNDS_BASE_URL.rstrip("/") if settings.SOUNDS_BASE_URL else ""
    return f"{base}/sounds/{filename}"


# Built-in high quality baby sleep sounds catalog
SOUNDS_CATALOG: List[SoundItemResponse] = [
    SoundItemResponse(
        id="snd_pink_432",
        sound_type=SoundType.PINK_NOISE_432HZ,
        title="432Hz Derin Pembe Gürültü (Pink Noise)",
        description="Bebeklerin beyin dalgalarını sakinleştiren ve derin NREM uykusunu destekleyen doğal 432Hz frekansı.",
        duration_seconds=3600,
        category="Gürültü Frekansları",
        frequency_hz=432,
        stream_url=_sound_url("pink_noise_432hz.mp3"),
        is_premium=False,
    ),
    SoundItemResponse(
        id="snd_womb_heartbeat",
        sound_type=SoundType.WOMB_SOUNDS,
        title="Anne Karnı & Kalp Atışı (Womb Sounds)",
        description="Anne karnındaki güvenli ve tanıdık kan akışı ve nabız ritmini simüle eden akustik kayıt.",
        duration_seconds=3600,
        category="Rahatlatıcı Ortam",
        frequency_hz=None,
        stream_url=_sound_url("womb_sounds.mp3"),
        is_premium=False,
    ),
    SoundItemResponse(
        id="snd_heartbeat_calm",
        sound_type=SoundType.HEARTBEAT_CALM,
        title="Sakin Kalp Atışı (Heartbeat Calm)",
        description="65 BPM ritmik kalp atışı — açlık ve huzursuzluk durumunda bebeği sakinleştiren anne kalbinin sesi.",
        duration_seconds=3600,
        category="Rahatlatıcı Ortam",
        frequency_hz=None,
        stream_url=_sound_url("heartbeat_calm.mp3"),
        is_premium=False,
    ),
    SoundItemResponse(
        id="snd_shushing_loop",
        sound_type=SoundType.SHUSHING_RHYTHMIC,
        title="Ritmik Pışpışlama (Shushing Engine)",
        description="Dr. Harvey Karp 5S metoduna uygun ritmik ve sakinleştirici pışpışlama sesi.",
        duration_seconds=1800,
        category="Sakinleştirici",
        frequency_hz=None,
        stream_url=_sound_url("shushing_rhythmic.mp3"),
        is_premium=False,
    ),
    SoundItemResponse(
        id="snd_white_noise",
        sound_type=SoundType.WHITE_NOISE,
        title="Klasik Beyaz Gürültü (White Noise)",
        description="Dış ortamdaki ani sesleri ve gürültüleri maskeleyen stabil ses perdesi.",
        duration_seconds=3600,
        category="Gürültü Frekansları",
        frequency_hz=None,
        stream_url=_sound_url("white_noise.mp3"),
        is_premium=False,
    ),
    SoundItemResponse(
        id="snd_brown_noise",
        sound_type=SoundType.BROWN_NOISE,
        title="Kahverengi Gürültü (Brown Noise)",
        description="Daha kalın ve şelale benzeri tok frekanslar sunan derin rahatlama gürültüsü.",
        duration_seconds=3600,
        category="Gürültü Frekansları",
        frequency_hz=None,
        stream_url=_sound_url("brown_noise.mp3"),
        is_premium=True,
    ),
    SoundItemResponse(
        id="snd_rain_calm",
        sound_type=SoundType.RAIN_GENTLE,
        title="Hafif Yağmur & Doğa",
        description="Cama vuran yumuşak yağmur damlaları ve huzurlu doğa atmosferi.",
        duration_seconds=3600,
        category="Doğa Sesleri",
        frequency_hz=None,
        stream_url=_sound_url("rain_gentle.mp3"),
        is_premium=False,
    ),
    SoundItemResponse(
        id="snd_brahms_lullaby",
        sound_type=SoundType.BRAHMS_LULLABY,
        title="Brahms Ninni (Müzik Kutusu)",
        description="Klasik müzik kutusu tınısıyla çalınan uyku öncesi sakinleştirici ninni.",
        duration_seconds=1200,
        category="Ninniler",
        frequency_hz=None,
        stream_url=_sound_url("brahms_lullaby.mp3"),
        is_premium=True,
    ),
]


@router.get("/list", response_model=SoundListResponse)
def list_soothing_sounds(
    category: Optional[str] = Query(None, description="Kategoriye göre filtrele"),
    current_user: User = Depends(get_current_user),
):
    """
    Get all available soothing sleep and calming audio tracks with streaming URLs.
    """
    sounds = SOUNDS_CATALOG
    if category:
        sounds = [s for s in sounds if s.category.lower() == category.lower()]

    categories = list(set(s.category for s in SOUNDS_CATALOG))

    return SoundListResponse(
        total=len(sounds),
        categories=categories,
        sounds=sounds,
    )
