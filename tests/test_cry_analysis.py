# -*- coding: utf-8 -*-
import io
import math
import struct
import unittest
import wave
from app.services.cry_analysis import CryAnalysisService
from app.models.enums import CryType


def create_synthetic_cry_wav_bytes():
    """Generates a 2-second in-memory synthetic baby cry wav byte stream."""
    sample_rate = 22050
    duration_sec = 2.0
    num_samples = int(sample_rate * duration_sec)
    
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        
        frames = bytearray()
        for i in range(num_samples):
            t = float(i) / sample_rate
            # 450 Hz pitch fundamental + 900 Hz formant with tremolo
            tremolo = 1.0 + 0.3 * math.sin(2.0 * math.pi * 5.0 * t)
            sample_val = math.sin(2.0 * math.pi * 450.0 * t) * tremolo * 0.4
            sample_val += 0.2 * math.sin(2.0 * math.pi * 900.0 * t)
            # Clip between -1.0 and 1.0
            sample_val = max(-1.0, min(1.0, sample_val))
            int_val = int(sample_val * 32767.0)
            frames.extend(struct.pack("<h", int_val))
            
        wav_file.writeframes(frames)
        
    buf.seek(0)
    return buf.read()


class TestCryAnalysisService(unittest.TestCase):
    def test_cry_feature_extraction_and_probabilities(self):
        """Test feature extraction and probability calculation with synthetic wave bytes."""
        wav_bytes = create_synthetic_cry_wav_bytes()
        _, duration, features = CryAnalysisService.extract_features(wav_bytes)

        self.assertGreater(duration, 1.5)
        self.assertEqual(features["sample_rate"], 22050)
        self.assertIn("zcr_mean", features)
        self.assertIn("spectral_centroid_mean", features)
        self.assertEqual(len(features["mfcc_mean_0_to_12"]), 13)

        # Check probabilities
        probs = CryAnalysisService.evaluate_probabilities(features)
        self.assertEqual(len(probs), 6)
        
        # Verify probability distribution sums close to 1.0
        total_prob = sum(p.likelihood for p in probs)
        self.assertTrue(0.95 <= total_prob <= 1.05)

        # Check top cause
        top_cause = probs[0].cause
        self.assertIn(
            top_cause,
            [
                CryType.HUNGRY,
                CryType.TIRED,
                CryType.PAIN_COLIC,
                CryType.DISCOMFORT,
                CryType.BURPING_NEEDED,
                CryType.OVERSTIMULATED,
            ],
        )

    def test_gemini_key_pool_caching_and_proxy_rate_limit_keys(self):
        """Verify in-memory Gemini key pool rotation, AQ. key acceptance, and CGNAT/proxy-safe rate limit keys."""
        import os
        from starlette.requests import Request
        from app.services.ai_sleep_coach import (
            _get_gemini_api_key_pool,
            _get_ordered_gemini_keys_for_request,
            get_ai_tier_metrics_snapshot,
            record_ai_tier_metric,
        )
        from app.api.v1.endpoints.coach import _build_coach_rate_limit_key
        from app.api.v1.endpoints.cry_analysis import _build_cry_rate_limit_key, _extract_cry_client_ip
        from app.main import _extract_real_client_ip

        old_keys = os.environ.get("GEMINI_API_KEYS")
        try:
            os.environ["GEMINI_API_KEYS"] = "AQ.TestKeyOne1234567890123456,AQ.TestKeyTwo1234567890123456"
            pool = _get_gemini_api_key_pool(force_refresh=True)
            self.assertGreaterEqual(len(pool), 2)
            self.assertEqual(pool[0], "AQ.TestKeyOne1234567890123456")
            self.assertEqual(pool[1], "AQ.TestKeyTwo1234567890123456")

            first_rot = _get_ordered_gemini_keys_for_request()
            second_rot = _get_ordered_gemini_keys_for_request()
            self.assertNotEqual(first_rot[0], second_rot[0])
        finally:
            if old_keys is None:
                os.environ.pop("GEMINI_API_KEYS", None)
            else:
                os.environ["GEMINI_API_KEYS"] = old_keys
            _get_gemini_api_key_pool(force_refresh=True)

        scope_mom = {
            "type": "http",
            "client": ("10.0.0.1", 12345),
            "headers": [
                (b"x-forwarded-for", b"203.0.113.5, 198.51.100.42"),
                (b"x-device-uid", b"device_mom_01"),
            ],
        }
        scope_dad = {
            "type": "http",
            "client": ("10.0.0.1", 12345),
            "headers": [
                (b"x-forwarded-for", b"203.0.113.5, 198.51.100.42"),
                (b"x-device-uid", b"device_dad_02"),
            ],
        }
        req_mom = Request(scope_mom)
        req_dad = Request(scope_dad)

        self.assertEqual(_extract_real_client_ip(req_mom), "198.51.100.42")
        self.assertEqual(_extract_cry_client_ip(req_mom), "198.51.100.42")
        key_mom = _build_coach_rate_limit_key(req_mom, scope_hint="Can:mother")
        key_dad = _build_coach_rate_limit_key(req_dad, scope_hint="Can:father")
        self.assertNotEqual(key_mom, key_dad)
        cry_key_mom = _build_cry_rate_limit_key(req_mom, scope_hint="1")
        cry_key_dad = _build_cry_rate_limit_key(req_dad, scope_hint="1")
        self.assertNotEqual(cry_key_mom, cry_key_dad)

        before_m = get_ai_tier_metrics_snapshot().get("dadi_tier1_gemini", 0)
        record_ai_tier_metric("dadi_tier1_gemini")
        after_m = get_ai_tier_metrics_snapshot().get("dadi_tier1_gemini", 0)
        self.assertEqual(after_m, before_m + 1)


if __name__ == "__main__":
    unittest.main()
