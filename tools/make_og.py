#!/usr/bin/env python3
"""LINK_PREVIEW_V1 share image + icons for MiningNewsTerminal (2026-09-16).

Draws static/og-default.png (1200x630) in the same layout as MineTerminal Pro's
/static/og-default.png: red top rule, logo + wordmark, bold tagline, two grey
feature lines, faint chart panel on the right, dark footer band with the domain
and exchanges. Also writes apple-touch-icon.png (180) and favicon.ico (48/32/16)
from the logo embedded in static/mnt-logo.svg.

Usage: make_og.py FONT_TTF LOGO_SVG OUT_DIR
FONT_TTF is Roboto's variable font from github.com/google/fonts (ofl/roboto).
"""
import base64, math, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT, LOGO_SVG, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
W, H, S = 1200, 630, 2
RED = (215, 25, 32); INK = (26, 26, 26); SOFT = (68, 68, 68); BAND = (28, 28, 28)

b64 = re.search(r'base64,([A-Za-z0-9+/=]+)', Path(LOGO_SVG).read_text()).group(1)
import io
LOGO = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")


def font(size, wght):
    f = ImageFont.truetype(FONT, size * S)
    f.set_variation_by_axes([wght, 100])
    return f


def share_image():
    im = Image.new("RGB", (W * S, H * S), "white")
    d = ImageDraw.Draw(im)
    for gx in range(640, W, 80):
        d.line([(gx * S, 15 * S), (gx * S, 560 * S)], fill=(243, 243, 243), width=2 * S)
    P = [(600, 445), (620, 432), (700, 380), (802, 339), (880, 372), (990, 470),
         (1070, 432), (1120, 420), (1200, 348), (1230, 320)]
    pts = []
    for j in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[j - 1], P[j], P[j + 1], P[j + 2]
        for k in range(24):
            t = k / 24
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t * t + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t ** 3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t * t + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t ** 3)
            pts.append((x * S, y * S))
    pts.append((1200 * S, 348 * S))
    d.polygon(pts + [(W * S, 560 * S), (620 * S, 560 * S)], fill=(246, 246, 246))
    d.line(pts, fill=(240, 190, 190), width=3 * S, joint="curve")
    d.rectangle([0, 0, W * S, 14 * S], fill=RED)
    ls = 92 * S
    logo = LOGO.resize((ls, ls), Image.LANCZOS)
    im.paste(logo, (84 * S, 124 * S), logo)
    d.text((196 * S, 170 * S), "MiningNewsTerminal", font=font(76, 800), fill=INK, anchor="lm")
    d.text((85 * S, 292 * S), "The junior mining news terminal", font=font(40, 700), fill=INK, anchor="lm")
    fl = font(31, 400)
    for k, line in enumerate(["News releases · Drill results · Financings",
                              "Resources · M&A · Management changes"]):
        d.text((85 * S, (350 + 46 * k) * S), line, font=fl, fill=SOFT, anchor="lm")
    d.rectangle([0, 560 * S, W * S, H * S], fill=BAND)
    d.text((85 * S, 595 * S), "miningnewsterminal.com", font=font(28, 700), fill="white", anchor="lm")
    d.text((1115 * S, 595 * S), "CSE · TSXV · TSX", font=font(26, 400), fill=(215, 215, 215), anchor="rm")
    im = im.resize((W, H), Image.LANCZOS)
    im.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(OUT / "og-default.png", optimize=True)


def icons():
    bg = Image.new("RGBA", LOGO.size, "white")
    bg.alpha_composite(LOGO)
    bg.convert("RGB").resize((180, 180), Image.LANCZOS).quantize(colors=32, dither=Image.Dither.NONE).save(OUT / "apple-touch-icon.png", optimize=True)
    LOGO.resize((48, 48), Image.LANCZOS).save(OUT / "favicon.ico", sizes=[(48, 48), (32, 32), (16, 16)])


OUT.mkdir(parents=True, exist_ok=True)
share_image()
icons()
for n in ("og-default.png", "apple-touch-icon.png", "favicon.ico"):
    p = OUT / n
    print(n, p.stat().st_size, Image.open(p).size)
