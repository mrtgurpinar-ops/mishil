# -*- coding: utf-8 -*-
import os
import math
from PIL import Image, ImageDraw

assets_dir = r"c:\Users\MSI-NB\OneDrive\Desktop\antigravity_core\projects\mishil\mobile\assets"
os.makedirs(assets_dir, exist_ok=True)

def draw_crescent_moon(draw, center, radius, color, bg_color):
    cx, cy = center
    # Outer circle
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color)
    # Inner cutout circle for crescent effect
    cutout_offset = int(radius * 0.45)
    cutout_radius = int(radius * 0.88)
    draw.ellipse([cx - cutout_radius + cutout_offset, cy - cutout_radius - cutout_offset, 
                  cx + cutout_radius + cutout_offset, cy + cutout_radius - cutout_offset], fill=bg_color)

# 1. Official App Store & Google Play Icon (1024x1024)
icon = Image.new("RGBA", (1024, 1024), (20, 27, 46, 255)) # #141B2E
draw = ImageDraw.Draw(icon)
# Glowing outer halo
draw.ellipse([212, 212, 812, 812], fill=(232, 168, 85, 35))
draw.ellipse([262, 262, 762, 762], fill=(232, 168, 85, 75))
# Crescent Moon
draw_crescent_moon(draw, (512, 512), 200, (232, 168, 85, 255), (20, 27, 46, 255))
# Tiny sparkling stars
draw.ellipse([700, 360, 716, 376], fill=(255, 255, 255, 220))
draw.ellipse([320, 680, 332, 692], fill=(255, 255, 255, 180))

icon_path = os.path.join(assets_dir, "icon.png")
icon.save(icon_path, "PNG")
print("Saved App Store 1024x1024 icon to:", icon_path)

# 2. Adaptive Foreground Icon (1024x1024 transparent)
adaptive = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
draw_ad = ImageDraw.Draw(adaptive)
draw_crescent_moon(draw_ad, (512, 512), 180, (232, 168, 85, 255), (0, 0, 0, 0))
draw_ad.ellipse([680, 380, 694, 394], fill=(255, 255, 255, 220))
adaptive_path = os.path.join(assets_dir, "adaptive-icon.png")
adaptive.save(adaptive_path, "PNG")
print("Saved Adaptive Icon to:", adaptive_path)

# 3. High-Res Splash Screen (1284x2778 for iPhone 15 Pro Max / Android)
splash = Image.new("RGBA", (1284, 2778), (20, 27, 46, 255))
draw_sp = ImageDraw.Draw(splash)
# Large ambient glow
draw_sp.ellipse([342, 1089, 942, 1689], fill=(232, 168, 85, 30))
draw_sp.ellipse([442, 1189, 842, 1589], fill=(232, 168, 85, 60))
# Center Moon
draw_crescent_moon(draw_sp, (642, 1389), 160, (232, 168, 85, 255), (20, 27, 46, 255))
# Little stars
draw_sp.ellipse([780, 1280, 796, 1296], fill=(255, 255, 255, 200))
draw_sp.ellipse([500, 1520, 512, 1532], fill=(255, 255, 255, 160))

splash_path = os.path.join(assets_dir, "splash.png")
splash.save(splash_path, "PNG")
print("Saved Splash Screen to:", splash_path)

# 4. Notification Icon (96x96 monochrome)
notif = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
draw_notif = ImageDraw.Draw(notif)
draw_crescent_moon(draw_notif, (48, 48), 36, (255, 255, 255, 255), (0, 0, 0, 0))
notif_path = os.path.join(assets_dir, "notification-icon.png")
notif.save(notif_path, "PNG")
print("Saved Notification Icon to:", notif_path)
