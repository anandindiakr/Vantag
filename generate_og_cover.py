"""Generate 1200x630 Open Graph cover for social-media link previews."""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.join(os.path.dirname(__file__), "frontend", "web", "public", "og-cover.png")
W, H = 1200, 630

img = Image.new("RGB", (W, H), (11, 16, 32))  # vantag dark
d = ImageDraw.Draw(img, "RGBA")

# Gradient background (diagonal)
for y in range(H):
    t = y / H
    r = int(11 + (139 - 11) * (1 - t) * 0.25)
    g = int(16 + (92 - 16) * (1 - t) * 0.25)
    b = int(32 + (246 - 32) * (1 - t) * 0.25)
    d.rectangle([0, y, W, y + 1], fill=(r, g, b))

# Big violet orb top-right
for r in range(300, 0, -4):
    alpha = int(80 * (r / 300))
    d.ellipse([W - 250 - r, -100 - r, W - 250 + r, -100 + r],
              fill=(139, 92, 246, alpha))

# Emerald orb bottom-left
for r in range(250, 0, -4):
    alpha = int(60 * (r / 250))
    d.ellipse([-100 - r, H - 50 - r, -100 + r, H - 50 + r],
              fill=(16, 185, 129, alpha))

# Try to load a decent font; fall back to default if absent
def load(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()

font_brand = load(52, bold=True)
font_title = load(78, bold=True)
font_sub = load(36)
font_tag = load(28)

# Brand pill
d.rounded_rectangle([60, 55, 370, 115], radius=30,
                    fill=(139, 92, 246, 220))
d.text((95, 71), "VANTAG", font=font_brand, fill=(255, 255, 255))

# Main headline
d.text((60, 200), "DIY AI Security", font=font_title, fill=(255, 255, 255))
d.text((60, 290), "for Shops & Offices", font=font_title, fill=(255, 255, 255))

# Subtitle
d.text((60, 410), "Any IP camera → 24/7 AI guardian",
       font=font_sub, fill=(200, 200, 220))
d.text((60, 458), "Theft  •  Loitering  •  Falls  •  Empty Shelves",
       font=font_sub, fill=(200, 200, 220))

# Bottom tag line
d.rectangle([0, H - 70, W, H], fill=(0, 0, 0, 180))
d.text((60, H - 52), "30-min setup  |  works with any IP camera  |  retail-vantag.com",
       font=font_tag, fill=(255, 255, 255))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT, "PNG", optimize=True)
print(f"Saved: {OUT}")
print(f"Size: {os.path.getsize(OUT) // 1024} KB")
