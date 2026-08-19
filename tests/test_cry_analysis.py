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
        self.assertEqual(len(probs), 5)
        
        # Verify probability distribution sums close to 1.0
        total_prob = sum(p.likelihood for p in probs)
        self.assertTrue(0.95 <= total_prob <= 1.05)

        # Check top cause
        top_cause = probs[0].cause
        self.assertIn(top_cause, [CryType.HUNGRY, CryType.TIRED, CryType.PAIN_COLIC, CryType.DISCOMFORT, CryType.BURPING_NEEDED])


if __name__ == "__main__":
    unittest.main()
