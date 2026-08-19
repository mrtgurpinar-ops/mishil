# -*- coding: utf-8 -*-
import os
import urllib.request

sounds_dir = r"c:\Users\MSI-NB\OneDrive\Desktop\antigravity_core\projects\mishil\mobile\web-preview\sounds"
os.makedirs(sounds_dir, exist_ok=True)

# High-quality real acoustic field recordings from open-source repositories (Wikimedia Commons & Public Domain CDNs)
SOUND_URLS = {
    # 1. Real Studio Rain & Distant Thunder (Lossless Natural Rain)
    "soft_rain.mp3": "https://upload.wikimedia.org/wikipedia/commons/e/eb/Rain_and_thunder.ogg",
    # 2. Real Heartbeat (Actual Medical Ultrasound Doppler & Stethoscope recording)
    "womb_heartbeat.mp3": "https://upload.wikimedia.org/wikipedia/commons/e/e0/Heartbeat_normal.ogg",
    # 3. Real Brown / Pink Noise
    "pink_432hz.mp3": "https://upload.wikimedia.org/wikipedia/commons/c/c2/Pink_noise.ogg",
    # 4. Fireplace Crackle (Real Campfire & Wood Crackle)
    "fireplace.mp3": "https://upload.wikimedia.org/wikipedia/commons/2/23/Fireplace_sound_1_min.ogg"
}

headers = {"User-Agent": "Mozilla/5.0"}

for fname, url in SOUND_URLS.items():
    dest = os.path.join(sounds_dir, fname)
    try:
        print(f"Downloading real acoustic sound: {fname} from {url}...")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        print(f"✅ Successfully saved {fname} ({os.path.getsize(dest)} bytes)")
    except Exception as e:
        print(f"❌ Failed to download {fname}:", e)
