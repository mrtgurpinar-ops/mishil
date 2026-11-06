import os
import sys
import wave
import io
import struct
import math
from fastapi.testclient import TestClient

# Ensure projects/mishil is on sys.path
MISHIL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MISHIL_ROOT not in sys.path:
    sys.path.insert(0, MISHIL_ROOT)

from app.main import app
from app.services.ai_sleep_coach import (
    normalize_lang,
    _calc_baby_details,
    _tier4_clinical_heuristic,
)
from app.services.cry_analysis import CryAnalysisService


def _generate_test_wav_bytes(freq_hz: float = 440.0, duration_sec: float = 0.6, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    num_samples = int(sample_rate * duration_sec)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            val = int(12000 * math.sin(2 * math.pi * freq_hz * (i / sample_rate)))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def test_normalize_lang():
    assert normalize_lang("tr") == "tr"
    assert normalize_lang("tr-TR") == "tr"
    assert normalize_lang("en") == "en"
    assert normalize_lang("en-US") == "en"
    assert normalize_lang("en-GB") == "en"
    assert normalize_lang("de-DE") == "en"
    assert normalize_lang(None) == "tr"


def test_calc_baby_details_bilingual():
    tr_info = _calc_baby_details("2026-08-01", manual_leap=None, lang="tr")
    en_info = _calc_baby_details("2026-08-01", manual_leap=None, lang="en")
    assert "Günlük" in tr_info["age_formatted"]
    assert "Days old" in en_info["age_formatted"]
    assert tr_info["wake_window_min"] == en_info["wake_window_min"]
    assert tr_info["leap_info"] != en_info["leap_info"]


def test_tier4_clinical_heuristic_bilingual():
    tr_reply = _tier4_clinical_heuristic(
        baby_name="Can",
        birth_date="2026-08-01",
        message="Bebeğim çok gazlı ve kolik yüzünden ağlıyor",
        user_role="mother",
        lang="tr",
    )
    en_reply = _tier4_clinical_heuristic(
        baby_name="Leo",
        birth_date="2026-08-01",
        message="My baby has gas and colic pain",
        user_role="mother",
        lang="en",
    )
    assert "Anneciğim" in tr_reply or "Sevgili" in tr_reply
    assert "Dear Mom" in en_reply
    assert "Wishing you sweet Mishil dreams" in en_reply


def test_cry_analysis_probabilities_bilingual():
    sample_features = {
        "spectral_centroid_mean": 2950.0,
        "zcr_mean": 0.14,
        "rms_mean": 0.08,
    }
    probs_tr = CryAnalysisService.evaluate_probabilities(sample_features, lang="tr")
    probs_en = CryAnalysisService.evaluate_probabilities(sample_features, lang="en")

    assert len(probs_tr) == len(probs_en) == 6
    assert probs_tr[0].cause == probs_en[0].cause
    assert probs_tr[0].description != probs_en[0].description


def test_coach_and_legal_endpoints_bilingual(monkeypatch):
    monkeypatch.setattr(CryAnalysisService, "_analyze_with_gemini_multimodal", classmethod(lambda cls, *args, **kwargs: None))
    client = TestClient(app)

    # Privacy & Terms pages contain both TR and EN toggles
    resp_priv = client.get("/privacy?lang=en")
    assert resp_priv.status_code == 200
    assert "Mışıl Baby: Privacy Policy" in resp_priv.text
    assert "Mışıl Baby: Gizlilik Politikası" in resp_priv.text

    resp_terms = client.get("/terms?lang=en")
    assert resp_terms.status_code == 200
    assert "Terms of Use & End User License Agreement (EULA)" in resp_terms.text

    # Cry Analysis endpoint with lang='en' (parameter name is 'file')
    wav_bytes = _generate_test_wav_bytes()
    resp_cry_en = client.post(
        "/api/v1/cry-analysis/analyze",
        data={"lang": "en"},
        files={"file": ("cry.wav", wav_bytes, "audio/wav")},
    )
    assert resp_cry_en.status_code == 200
    body_en = resp_cry_en.json()
    assert "medical diagnosis" in body_en["confidence_note"].lower()

    # Cry Analysis endpoint with lang='tr'
    resp_cry_tr = client.post(
        "/api/v1/cry-analysis/analyze",
        data={"lang": "tr"},
        files={"file": ("cry.wav", wav_bytes, "audio/wav")},
    )
    assert resp_cry_tr.status_code == 200
    body_tr = resp_cry_tr.json()
    assert body_tr["recommended_action"] != body_en["recommended_action"]
