from __future__ import annotations

from PIL import ImageFont

from bonecta.paths import NOTO_SANS_JP_PATH

# 同梱 Noto Sans JP VF のみ（端末・OS 差なし）
WEIGHT_LIGHT = 500  # テロップ（Medium 寄り）
WEIGHT_REGULAR = 400  # メタ・注釈
WEIGHT_MEDIUM = 500  # 本文寄り
WEIGHT_BOLD = 700  # 名前・CTA


def _require_noto() -> None:
    if not NOTO_SANS_JP_PATH.exists():
        raise FileNotFoundError(
            f"フォントが見つかりません: {NOTO_SANS_JP_PATH} "
            "(fonts/NotoSansJP-VF.ttf を配置してください)"
        )


def get_font_path() -> str:
    """互換用。常に同梱 Noto Sans JP を返す。"""
    _require_noto()
    return str(NOTO_SANS_JP_PATH)


def load_font(
    size: int,
    *,
    bold: bool = False,
    weight: int | None = None,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """UI 全般。bold=True → 700、指定なければ Regular(400)。"""
    _require_noto()
    w = weight if weight is not None else (WEIGHT_BOLD if bold else WEIGHT_REGULAR)
    font = ImageFont.truetype(str(NOTO_SANS_JP_PATH), size)
    if hasattr(font, "set_variation_by_axes"):
        font.set_variation_by_axes([float(w)])
    return font


def load_telop_font(
    size: int,
    *,
    weight: int = WEIGHT_LIGHT,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """字幕専用（やや細め）。"""
    return load_font(size, weight=weight)
