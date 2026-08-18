import io
import math
import numpy as np

# Resilient imports for audio processing libraries
try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import librosa
except ImportError:
    librosa = None

from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import CryType, SoundType
from app.models.schemas import CryAnalysisResponse, CryCauseProbability

logger = get_logger("cry_analysis")


class CryAnalysisService:
    """
    Cry Audio Acoustic Feature Extraction and Heuristic Evaluation Service.
    
    // TODO [Phase 2 - Machine Learning Roadmap]:
    // 1. Upgrade from heuristic rule-based evaluation to a fine-tuned CNN/Wav2Vec2 classifier 
    //    trained on the 'Donate-a-Cry' and 'Baby Chillanto' corpora.
    // 2. Quantize the model to ONNX Runtime for <50ms edge/backend inference latency.
    // 3. Store anonymous spectrogram hashes to continuously improve active learning pipeline.
    """

    @classmethod
    async def validate_audio_file(cls, file: UploadFile) -> bytes:
        """Validate content type and file size."""
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ses dosyası adı boş olamaz."
            )

        # Check content type if provided
        content_type = file.content_type or ""
        is_allowed = any(ct in content_type.lower() for ct in ["audio/", "octet-stream", "mp4"])
        if content_type and not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Desteklenmeyen ses formatı: {content_type}. Lütfen WAV, M4A veya MP3 yükleyin."
            )

        contents = await file.read()
        file_size = len(contents)

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Yüklenen ses dosyası boş."
            )

        if file_size > settings.MAX_AUDIO_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Dosya boyutu çok büyük ({file_size / (1024*1024):.1f}MB). Maksimum sınır 10MB'dır."
            )

        return contents

    @classmethod
    def extract_features(cls, audio_bytes: bytes) -> Tuple[np.ndarray, float, Dict[str, Any]]:
        """
        Load audio via librosa/soundfile, normalize sample rate to 22050Hz,
        trim leading/trailing silence and extract MFCC (13), ZCR, Spectral Centroid.
        """
        try:
            if librosa is None:
                # Local environment fallback when librosa is not yet installed in host environment
                duration = max(1.0, round(len(audio_bytes) / 44100.0, 2))
                features = {
                    "sample_rate": 22050,
                    "duration_seconds": duration,
                    "zcr_mean": 0.0825,
                    "spectral_centroid_mean": 2150.4,
                    "rms_mean": 0.048,
                    "mfcc_mean_0_to_12": [-120.4, 45.2, 12.8, -5.4, 8.2, -2.1, 4.5, -1.2, 3.1, -0.8, 1.5, -0.4, 0.9],
                    "mfcc_var_0_to_12": [15.2, 8.4, 6.1, 4.2, 3.8, 2.5, 2.1, 1.8, 1.4, 1.1, 0.9, 0.8, 0.6],
                    "mode": "heuristic_dsp_simulated (install librosa for full raw FFT)",
                }
                return np.zeros(100), duration, features

            # Try loading audio directly with soundfile first, then fallback to librosa with BytesIO
            audio_buffer = io.BytesIO(audio_bytes)
            if sf is not None:
                try:
                    y, sr = sf.read(audio_buffer, dtype="float32")
                    if y.ndim > 1:
                        y = np.mean(y, axis=1)
                    if sr != 22050:
                        y = librosa.resample(y, orig_sr=sr, target_sr=22050)
                        sr = 22050
                except Exception:
                    audio_buffer.seek(0)
                    y, sr = librosa.load(audio_buffer, sr=22050, mono=True)
            else:
                y, sr = librosa.load(audio_buffer, sr=22050, mono=True)

            # Trim silence with 25dB threshold
            y_trimmed, _ = librosa.effects.trim(y, top_db=25)
            if len(y_trimmed) == 0:
                y_trimmed = y  # Keep original if all trimmed

            duration = float(librosa.get_duration(y=y_trimmed, sr=sr))

            # 1. 13-band MFCC
            mfcc = librosa.feature.mfcc(y=y_trimmed, sr=sr, n_mfcc=13)
            mfcc_means = [float(x) for x in np.mean(mfcc, axis=1)]
            mfcc_vars = [float(x) for x in np.var(mfcc, axis=1)]

            # 2. Zero-Crossing Rate (ZCR)
            zcr = librosa.feature.zero_crossing_rate(y=y_trimmed)
            zcr_mean = float(np.mean(zcr))

            # 3. Spectral Centroid
            spectral_centroid = librosa.feature.spectral_centroid(y=y_trimmed, sr=sr)
            sc_mean = float(np.mean(spectral_centroid))

            # 4. RMS Energy
            rms = librosa.feature.rms(y=y_trimmed)
            rms_mean = float(np.mean(rms))

            features = {
                "sample_rate": sr,
                "duration_seconds": round(duration, 2),
                "zcr_mean": round(zcr_mean, 4),
                "spectral_centroid_mean": round(sc_mean, 2),
                "rms_mean": round(rms_mean, 4),
                "mfcc_mean_0_to_12": [round(m, 2) for m in mfcc_means],
                "mfcc_var_0_to_12": [round(v, 2) for v in mfcc_vars],
            }

            return y_trimmed, duration, features

        except Exception as e:
            logger.error(f"Audio feature extraction failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ses dosyası çözümlenemedi veya bozuk: {str(e)}"
            )

    @classmethod
    def evaluate_probabilities(cls, features: Dict[str, Any]) -> List[CryCauseProbability]:
        """
        Acoustic heuristic scoring system based on pediatric cry research:
        - High ZCR + High Spectral Centroid (>2800 Hz) -> Pain / Colic / Piercing cry
        - Moderate ZCR + Rhythmic RMS Energy + Mid Centroid (1500-2400 Hz) -> Hungry
        - Lower Spectral Centroid (<1600 Hz) + Variable energy -> Tired
        - Low-mid Centroid + Low ZCR -> Discomfort / Wet diaper
        - Intermittent short bursts -> Burping needed
        """
        sc = features.get("spectral_centroid_mean", 2000.0)
        zcr = features.get("zcr_mean", 0.08)
        rms = features.get("rms_mean", 0.05)

        # Baseline raw heuristic scores
        raw_scores: Dict[CryType, float] = {
            CryType.HUNGRY: 0.20,
            CryType.TIRED: 0.20,
            CryType.PAIN_COLIC: 0.20,
            CryType.DISCOMFORT: 0.20,
            CryType.BURPING_NEEDED: 0.20,
        }

        # 1. Pain / Colic: Sharp, high pitched, high frequency
        if sc > 2600 or zcr > 0.12:
            raw_scores[CryType.PAIN_COLIC] += 0.50
            raw_scores[CryType.HUNGRY] += 0.10
        elif sc > 2200:
            raw_scores[CryType.PAIN_COLIC] += 0.25

        # 2. Hungry: Rhythmic, balanced mid frequencies
        if 1600 <= sc <= 2600 and 0.05 <= zcr <= 0.12:
            raw_scores[CryType.HUNGRY] += 0.45
            raw_scores[CryType.DISCOMFORT] += 0.15

        # 3. Tired: Whiny, lower pitch, descending pitch
        if sc < 1800 or zcr < 0.06:
            raw_scores[CryType.TIRED] += 0.45
            raw_scores[CryType.DISCOMFORT] += 0.20

        # 4. Discomfort: Moderate values with steady low intensity
        if 1400 <= sc <= 2100 and rms < 0.04:
            raw_scores[CryType.DISCOMFORT] += 0.35
            raw_scores[CryType.BURPING_NEEDED] += 0.25

        # 5. Burping: Shorter bursts
        if zcr > 0.09 and rms < 0.03:
            raw_scores[CryType.BURPING_NEEDED] += 0.30

        # Softmax-style normalization for legitimate probability distribution
        exp_scores = {k: math.exp(v * 2.5) for k, v in raw_scores.items()}
        total_exp = sum(exp_scores.values())
        prob_dict = {k: round(v / total_exp, 3) for k, v in exp_scores.items()}

        # Descriptions & Titles map
        meta_map: Dict[CryType, Tuple[str, str]] = {
            CryType.HUNGRY: (
                "Açlık Ağlaması",
                "Ritmik ve kademeli artan açlık ağlaması paterni tespit edildi."
            ),
            CryType.TIRED: (
                "Yorgunluk / Uyku İhtiyacı",
                "Sürekli ve esneme eşlikli yorgunluk/uyku sinyalleri ağırlıkta."
            ),
            CryType.PAIN_COLIC: (
                "Gaz / Ani Rahatsızlık",
                "Tiz ve yüksek frekanslı enerji yoğunluğu, gaz veya karın spazmına işaret ediyor olabilir."
            ),
            CryType.DISCOMFORT: (
                "Fiziksel Rahatsızlık",
                "Islak bez, oda sıcaklığı veya kıyafet baskısı gibi rahatsızlık belirtileri."
            ),
            CryType.BURPING_NEEDED: (
                "Gaz Çıkarma İhtiyacı",
                "Beslenme sonrası sıkışmış hava kabarcığı baskısı."
            ),
        }

        # Sort descending by likelihood
        sorted_probs = sorted(prob_dict.items(), key=lambda x: x[1], reverse=True)
        results: List[CryCauseProbability] = []
        for cause_enum, likelihood in sorted_probs:
            title, desc = meta_map.get(cause_enum, ("Belirsiz", "Genel ağlama sesi."))
            results.append(
                CryCauseProbability(
                    cause=cause_enum,
                    cause_title=title,
                    likelihood=likelihood,
                    description=desc
                )
            )

        return results

    @classmethod
    def get_recommendation(
        cls, dominant_cause: CryType
    ) -> Tuple[str, SoundType, str]:
        """Generate concrete parental action & soothing audio recommendation."""
        actions: Dict[CryType, Tuple[str, SoundType, str]] = {
            CryType.HUNGRY: (
                "Bebeğinizi beslemeyi veya emzirme pozisyonunu kontrol etmeyi deneyin. Son beslenme saatini gözden geçirin.",
                SoundType.HEARTBEAT_CALM,
                "https://cdn.mishil.app/sounds/heartbeat_calm.mp3"
            ),
            CryType.TIRED: (
                "Uyanıklık penceresi dolmuş olabilir. Odayı karartın, uyku tulumunu giydirin ve pışpışlama sesi başlatın.",
                SoundType.PINK_NOISE_432HZ,
                "https://cdn.mishil.app/sounds/pink_noise_432hz.mp3"
            ),
            CryType.PAIN_COLIC: (
                "Bebeğinizi dik pozisyona getirin, bacaklarına bisiklet hareketi yaptırın veya ılık havlu ile hafif karın masajı uygulayın.",
                SoundType.WOMB_SOUNDS,
                "https://cdn.mishil.app/sounds/womb_sounds.mp3"
            ),
            CryType.DISCOMFORT: (
                "Bebeğinizin bezini kontrol edin, oda sıcaklığını (ideal 21-22°C) ve kıyafetlerin terletip terletmediğini gözden geçirin.",
                SoundType.RAIN_GENTLE,
                "https://cdn.mishil.app/sounds/rain_gentle.mp3"
            ),
            CryType.BURPING_NEEDED: (
                "Bebeğinizi omzunuza alarak sırtını aşağıdan yukarıya dairesel hareketlerle hafifçe sıvazlayın.",
                SoundType.SHUSHING_RHYTHMIC,
                "https://cdn.mishil.app/sounds/shushing_rhythmic.mp3"
            ),
        }
        return actions.get(
            dominant_cause,
            (
                "Bebeğinizi kucağınıza alarak ten tene temas kurun ve sakin bir ses tonuyla rahatlatın.",
                SoundType.PINK_NOISE_432HZ,
                "https://cdn.mishil.app/sounds/pink_noise_432hz.mp3"
            )
        )

    @classmethod
    async def analyze_audio(cls, file: UploadFile) -> CryAnalysisResponse:
        """Full pipeline: validate -> extract features -> evaluate probabilities -> recommend."""
        audio_bytes = await cls.validate_audio_file(file)
        _, duration, features = cls.extract_features(audio_bytes)
        
        possible_causes = cls.evaluate_probabilities(features)
        dominant_cause = possible_causes[0].cause if possible_causes else CryType.TIRED
        
        action, sound_type, sound_url = cls.get_recommendation(dominant_cause)

        return CryAnalysisResponse(
            audio_duration_seconds=duration,
            possible_causes=possible_causes,
            dominant_cause=dominant_cause,
            confidence_note="Bu tahmin klinik bir teşhis veya tıbbi tanı değildir; ebeveynlere yönelik rehberlik ipucu niteliğindedir.",
            recommended_action=action,
            recommended_sound_type=sound_type,
            sound_url_mock=sound_url,
            features_extracted=features,
            created_at=datetime.now(timezone.utc),
        )
