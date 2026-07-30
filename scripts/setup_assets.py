#!/usr/bin/env python3
"""img/logo.png と bgm/ のプレースホルダーを生成"""

from __future__ import annotations

import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont

from bonecta.fonts import get_font_path
from bonecta.paths import FONT_PATH, FONTS_DIR, LOGO_PNG_PATH

IMG_DIR = ROOT / "img"
BGM_DIR = ROOT / "bgm"
FONT = get_font_path()

FONT_URL = (
    "https://github.com/google/fonts/raw/main/ofl/zenkakugothicnew/ZenKakuGothicNew-Medium.ttf"
)


def create_font() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    if FONT_PATH.exists():
        print(f"Keep existing {FONT_PATH}")
        return
    print(f"Downloading {FONT_PATH.name} ...")
    req = urllib.request.Request(FONT_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        FONT_PATH.write_bytes(resp.read())
    print(f"Created {FONT_PATH}")


def create_logo() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    if LOGO_PNG_PATH.exists():
        print(f"Keep existing {LOGO_PNG_PATH}")
        return
    logo = Image.new("RGBA", (320, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo)
    try:
        font_en = ImageFont.truetype(FONT, 44)
        font_ja = ImageFont.truetype(FONT, 24)
    except OSError:
        font_en = font_ja = ImageFont.load_default()
    draw.text((0, 8), "Bonecta", fill=(230, 0, 18, 255), font=font_en)
    draw.text((0, 56), "ボネクタ", fill=(230, 0, 18, 255), font=font_ja)
    logo.save(LOGO_PNG_PATH)
    print(f"Created {LOGO_PNG_PATH} (透過・赤背景なし)")


def create_bgm() -> None:
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    out = BGM_DIR / "sample_bgm.mp3"
    if out.exists():
        print(f"BGM already exists: {out}")
        return
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=554:duration=30",
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2,volume=0.08",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    print(f"Created {out}")


if __name__ == "__main__":
    create_font()
    create_logo()
    create_bgm()
