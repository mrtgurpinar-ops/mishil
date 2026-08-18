import io
import pytest
from app.services.cry_analysis import CryAnalysisService
from app.models.enums import CryType


def test_cry_feature_extraction_and_probabilities(synthetic_cry_wav_bytes):
    """Test feature extraction and probability calculation with synthetic wave bytes."""
    _, duration, features = CryAnalysisService.extract_features(synthetic_cry_wav_bytes)

    assert duration > 1.5
    assert features["sample_rate"] == 22050
    assert "zcr_mean" in features
    assert "spectral_centroid_mean" in features
    assert len(features["mfcc_mean_0_to_12"]) == 13

    # Check probabilities
    probs = CryAnalysisService.evaluate_probabilities(features)
    assert len(probs) == 5
    
    # Verify probability distribution sums close to 1.0
    total_prob = sum(p.likelihood for p in probs)
    assert 0.95 <= total_prob <= 1.05

    # Check top cause
    top_cause = probs[0].cause
    assert top_cause in [CryType.HUNGRY, CryType.TIRED, CryType.PAIN_COLIC, CryType.DISCOMFORT, CryType.BURPING_NEEDED]


def test_cry_analysis_api_endpoint(client, synthetic_cry_wav_bytes):
    """Test POST /api/v1/cry-analysis/analyze with valid audio upload."""
    # First register user to get token
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": "mom@mishil.app", "password": "password123", "full_name": "Ayşe Yılmaz"}
    )
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("baby_cry.wav", io.BytesIO(synthetic_cry_wav_bytes), "audio/wav")}
    response = client.post("/api/v1/cry-analysis/analyze", headers=headers, files=files)

    assert response.status_code == 200
    data = response.json()
    assert "possible_causes" in data
    assert "dominant_cause" in data
    assert "confidence_note" in data
    assert "recommended_action" in data
    assert "recommended_sound_type" in data
    assert len(data["possible_causes"]) > 0


def test_cry_analysis_empty_file(client):
    """Test empty audio file rejection with 400 Bad Request."""
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": "test_empty@mishil.app", "password": "password123"}
    )
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("empty.wav", io.BytesIO(b""), "audio/wav")}
    response = client.post("/api/v1/cry-analysis/analyze", headers=headers, files=files)

    assert response.status_code == 400
    assert "boş" in response.json()["message"].lower()


def test_cry_analysis_file_too_large(client):
    """Test oversized file (>10MB) rejection with 413 Payload Too Large."""
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": "test_large@mishil.app", "password": "password123"}
    )
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 11 MB dummy bytes
    large_payload = b"0" * (11 * 1024 * 1024)
    files = {"file": ("huge.wav", io.BytesIO(large_payload), "audio/wav")}
    response = client.post("/api/v1/cry-analysis/analyze", headers=headers, files=files)

    assert response.status_code == 413
    assert "büyük" in response.json()["message"].lower()
