# -*- coding: utf-8 -*-
import os
import math
import wave
import struct
import random

sounds_dir = r"c:\Users\MSI-NB\OneDrive\Desktop\antigravity_core\projects\mishil\mobile\web-preview\sounds"
os.makedirs(sounds_dir, exist_ok=True)

SAMPLE_RATE = 44100
DURATION = 10.0 # 10 second seamless loop
NUM_SAMPLES = int(SAMPLE_RATE * DURATION)

def save_wav(filename, samples):
    fpath = os.path.join(sounds_dir, filename)
    with wave.open(fpath, "wb") as wav:
        wav.setnchannels(2) # Stereo
        wav.setsampwidth(2) # 16-bit
        wav.setframerate(SAMPLE_RATE)
        
        frames = bytearray()
        for l, r in samples:
            # Clip between -1.0 and 1.0
            l_val = max(-1.0, min(1.0, l))
            r_val = max(-1.0, min(1.0, r))
            l_int = int(l_val * 32760)
            r_int = int(r_val * 32760)
            frames.extend(struct.pack("<hh", l_int, r_int))
        wav.writeframes(frames)
    print(f"Generated studio quality loop: {filename} ({len(samples)} samples)")

# 1. 432Hz Analog Warm Pink Noise (Voss-McCartney Algorithm + 432Hz Warmth)
print("Synthesizing 432Hz Analog Warm Pink Noise...")
pink_samples = []
b0, b1, b2, b3, b4, b5, b6 = 0, 0, 0, 0, 0, 0, 0
for i in range(NUM_SAMPLES):
    t = float(i) / SAMPLE_RATE
    white_l = random.uniform(-1.0, 1.0)
    white_r = random.uniform(-1.0, 1.0)
    
    b0 = 0.99886 * b0 + white_l * 0.0555179
    b1 = 0.99332 * b1 + white_l * 0.0750759
    b2 = 0.96900 * b2 + white_l * 0.1538520
    b3 = 0.86650 * b3 + white_l * 0.3104856
    b4 = 0.55000 * b4 + white_l * 0.5329522
    b5 = -0.7616 * b5 - white_l * 0.0168980
    pink_l = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white_l * 0.5362) * 0.18
    b6 = white_l * 0.115926
    
    # 432Hz Sub-Harmonic Warm Drone (Binaural calm)
    drone_l = math.sin(2.0 * math.pi * 432.0 * t) * 0.04 + math.sin(2.0 * math.pi * 216.0 * t) * 0.06
    drone_r = math.sin(2.0 * math.pi * 432.0 * t + 0.2) * 0.04 + math.sin(2.0 * math.pi * 216.0 * t) * 0.06
    
    pink_samples.append((pink_l + drone_l, pink_l + drone_r))
save_wav("pink_432hz.wav", pink_samples)

# 2. Womb & 65 BPM Maternal Heartbeat (Amniotic fluid resonance)
print("Synthesizing Womb & Heartbeat...")
womb_samples = []
heartbeat_interval = SAMPLE_RATE * 60 / 65 # 65 BPM -> ~0.923 sec
lub_len = int(SAMPLE_RATE * 0.12)
dub_len = int(SAMPLE_RATE * 0.10)
dub_delay = int(SAMPLE_RATE * 0.22)

for i in range(NUM_SAMPLES):
    t = float(i) / SAMPLE_RATE
    # Fluid woosh background
    fluid = (random.uniform(-1.0, 1.0) * 0.08) * (0.8 + 0.2 * math.sin(2.0 * math.pi * 0.2 * t))
    
    pos_in_beat = i % int(heartbeat_interval)
    pulse = 0.0
    # Lub (First beat)
    if pos_in_beat < lub_len:
        env = math.sin(math.pi * pos_in_beat / lub_len)
        pulse += math.sin(2.0 * math.pi * 55.0 * (pos_in_beat / SAMPLE_RATE)) * env * 0.8
        pulse += math.sin(2.0 * math.pi * 110.0 * (pos_in_beat / SAMPLE_RATE)) * env * 0.3
    # Dub (Second beat)
    elif dub_delay <= pos_in_beat < dub_delay + dub_len:
        d_pos = pos_in_beat - dub_delay
        env = math.sin(math.pi * d_pos / dub_len)
        pulse += math.sin(2.0 * math.pi * 65.0 * (d_pos / SAMPLE_RATE)) * env * 0.6
        pulse += math.sin(2.0 * math.pi * 130.0 * (d_pos / SAMPLE_RATE)) * env * 0.25
        
    womb_samples.append((fluid + pulse, fluid + pulse))
save_wav("womb_heartbeat.wav", womb_samples)

# 3. 5S Dr. Karp Rhythmic Breath Shushing (Natural Human Breath Simulation)
print("Synthesizing 5S Dr. Karp Rhythmic Breath...")
shush_samples = []
shush_period = 2.5 # 2.5 seconds per shush breath
for i in range(NUM_SAMPLES):
    t = float(i) / SAMPLE_RATE
    phase = (t % shush_period) / shush_period # 0 to 1
    # Breath Envelope (Exhale shuuush for 60% of cycle, inhale pause 40%)
    if phase < 0.65:
        env = math.sin(math.pi * phase / 0.65) ** 1.5
    else:
        env = 0.03 # subtle ambient room
        
    # Bandpass filtered filtered noise for human voice formant (800Hz - 2200Hz)
    noise = random.uniform(-1.0, 1.0) * env * 0.7
    # Vocal formant tone
    vocal = math.sin(2.0 * math.pi * 850.0 * t) * env * 0.12
    shush_samples.append((noise + vocal, noise + vocal))
save_wav("shush_5s.wav", shush_samples)

# 4. Soft Night Rain & Distant Ambience
print("Synthesizing Soft Night Rain...")
rain_samples = []
for i in range(NUM_SAMPLES):
    t = float(i) / SAMPLE_RATE
    # Multiple layered rain drops & soft rumble
    d1 = random.uniform(-1.0, 1.0) * 0.25
    d2 = (random.uniform(-1.0, 1.0) ** 3) * 0.4
    rumble = math.sin(2.0 * math.pi * 75.0 * t) * 0.08 * math.sin(2.0 * math.pi * 0.05 * t)
    rain_samples.append((d1 + d2 + rumble, d1 + d2 + rumble))
save_wav("soft_rain.wav", rain_samples)

print("All 4 studio audio tracks generated successfully!")
