from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "img"
BGM_DIR = ROOT / "bgm"
FONTS_DIR = ROOT / "fonts"
# 同梱 Noto Sans JP VF のみ（端末差なし）。旧 FONT_PATH / TELOP_FONT_PATH は互換エイリアス
NOTO_SANS_JP_PATH = FONTS_DIR / "NotoSansJP-VF.ttf"
FONT_PATH = NOTO_SANS_JP_PATH
TELOP_FONT_PATH = NOTO_SANS_JP_PATH
LOGO_SVG_PATH = IMG_DIR / "logo.svg"
LOGO_PNG_PATH = IMG_DIR / "logo.png"
LOGO_PATH = LOGO_PNG_PATH  # backward compat
