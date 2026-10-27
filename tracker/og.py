"""Share images (Open Graph cards, 1200x630 PNG) with the current price and a 90-day trend line.
Uses Pillow when it's installed; otherwise pages simply go without an image."""
from pathlib import Path

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None


def _font(size, bold=True):
    for f in (FONTS if bold else FONTS[::-1]):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def card(path, title, big, sub, series=None, brand="", change=None):
    """Render one card. Returns True if written."""
    if Image is None:
        return False
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), (247, 247, 245))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=(36, 87, 214))
    d.text((64, 52), brand, font=_font(30), fill=(36, 87, 214))
    t = title
    f = _font(60)
    while d.textlength(t, font=f) > W - 128 and len(t) > 10:
        t = t[:-2]
    if t != title:
        t = t.rstrip() + "…"
    d.text((64, 110), t, font=f, fill=(22, 24, 29))
    d.text((64, 200), big, font=_font(120), fill=(22, 24, 29))
    if change is not None:
        col = (192, 57, 43) if change > 0.5 else (19, 131, 79) if change < -0.5 else (93, 99, 110)
        arrow = "▲" if change > 0.5 else "▼" if change < -0.5 else "•"
        x = 64 + d.textlength(big, font=_font(120)) + 30
        d.text((x, 262), f"{arrow} {abs(change):.1f}% 30d", font=_font(40), fill=col)
    d.text((64, 350), sub, font=_font(34, bold=False), fill=(93, 99, 110))
    if series and len(series) > 1:
        x0, y0, x1, y1 = 64, 430, W - 64, H - 60
        lo, hi = min(series), max(series)
        rng = (hi - lo) or 1
        pts = [(x0 + i * (x1 - x0) / (len(series) - 1), y1 - (v - lo) / rng * (y1 - y0)) for i, v in enumerate(series)]
        d.polygon(pts + [(x1, y1), (x0, y1)], fill=(222, 230, 250))
        d.line(pts, fill=(36, 87, 214), width=6, joint="curve")
    im.save(path, "PNG", optimize=True)
    return True
