from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from bonecta.fonts import load_font, load_telop_font
from bonecta.models import VideoPlan

WIDTH = 1080
HEIGHT = 1920

# 選挙ドットコム政治家ページ寄せ
SENKYO_GREEN = (112, 192, 64)  # #70C040
SENKYO_GREEN_DARK = (88, 158, 48)
TEXT_PRIMARY = (34, 34, 34)
TEXT_SECONDARY = (90, 90, 90)
# サイト外周・ページ背景に近い色（#ECECE0）
PAGE_BG = (236, 236, 224)
PAGE_BG_WASH_ALPHA = 88  # 本編・エンディングに薄く敷く透過

TELOP_MARGIN_X = 48
TELOP_MAX_WIDTH = WIDTH - TELOP_MARGIN_X * 2
TELOP_FONT_MAX = 50
TELOP_FONT_MIN = 32
TELOP_LINE_GAP = 10
TELOP_PAD_X = 30
TELOP_PAD_Y = 18
TELOP_STROKE = 0  # 字間計測用（描画は枠線に任せる）
TELOP_BORDER_WIDTH = 2
TELOP_LETTER_GAP = 1  # わずかな字間で軽く見せる
TELOP_BG_FILL = (255, 255, 255, 200)
AVATAR_SIZE = 96
BADGE_PAD_Y = 12
BADGE_GAP = 14
BADGE_SIDE_PAD = 22  # 左右余白
NAME_FONT_SIZE = 42
META_FONT_SIZE = 36


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _telop_line_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    if not text:
        return 0
    total = 0
    for i, ch in enumerate(text):
        total += _text_size(draw, ch, font)[0]
        if i < len(text) - 1:
            total += TELOP_LETTER_GAP
    return total


def _wrap_telop_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        if current and _telop_line_width(draw, trial, font) > max_width:
            lines.append(current)
            current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or [text]


def _telop_line_metrics(
    draw: ImageDraw.ImageDraw, line: str, font: ImageFont.ImageFont
) -> tuple[int, int, int]:
    """幅・高さ・ベースライン補正（bbox top）を返す。"""
    if not line:
        return 0, 0, 0
    tops: list[int] = []
    bottoms: list[int] = []
    for ch in line:
        b = draw.textbbox((0, 0), ch, font=font)
        tops.append(b[1])
        bottoms.append(b[3])
    return _telop_line_width(draw, line, font), max(bottoms) - min(tops), min(tops)


def _draw_telop_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
) -> None:
    x, y = xy
    for i, ch in enumerate(text):
        draw.text((x, y), ch, fill=fill, font=font)
        x += _text_size(draw, ch, font)[0]
        if i < len(text) - 1:
            x += TELOP_LETTER_GAP


def _fit_telop_layout(text: str) -> tuple[ImageFont.ImageFont, list[str]]:
    probe = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(probe)
    inner_max = TELOP_MAX_WIDTH - TELOP_PAD_X * 2

    for size in range(TELOP_FONT_MAX, TELOP_FONT_MIN - 1, -2):
        font = load_telop_font(size)
        lines = _wrap_telop_lines(draw, text, font, inner_max)
        if all(_telop_line_width(draw, line, font) <= inner_max for line in lines):
            return font, lines

    font = load_telop_font(TELOP_FONT_MIN)
    lines = _wrap_telop_lines(draw, text, font, inner_max)
    return font, lines


def _draw_stroked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    stroke: int = 2,
) -> None:
    x, y = xy
    for dx in range(-stroke, stroke + 1):
        for dy in range(-stroke, stroke + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 180))
    draw.text((x, y), text, font=font, fill=fill)


def _circle_mask(size: int, *, soft: bool = False) -> Image.Image:
    """直径 size の円マスク。soft=False なら縁をはっきり（リング密着用）。"""
    if not soft:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
        return mask
    supersample = 4
    mask_big = Image.new("L", (size * supersample, size * supersample), 0)
    ImageDraw.Draw(mask_big).ellipse(
        [0, 0, size * supersample - 1, size * supersample - 1],
        fill=255,
    )
    return mask_big.resize((size, size), Image.Resampling.LANCZOS)


def _make_circle_avatar(
    path: Path,
    size: int,
    *,
    soft_edge: bool = True,
    centering: tuple[float, float] = (0.5, 0.42),
) -> Image.Image:
    """指定 size にちょうど収まる円形アバター（カバー切り抜き）。顔が中心寄りになるようやや上を優先。"""
    src = Image.open(path).convert("RGB")
    fitted = ImageOps.fit(
        src,
        (size, size),
        method=Image.Resampling.LANCZOS,
        centering=centering,
    ).convert("RGBA")
    fitted.putalpha(_circle_mask(size, soft=soft_edge))
    return fitted


def _make_ringed_avatar(path: Path | None, size: int, ring: int, name: str = "") -> Image.Image:
    """緑リングと写真が同じ中心で密着したアバター（1px重ねて隙間防止）。"""
    outer = size + ring * 2
    green = Image.new("RGBA", (outer, outer), (0, 0, 0, 0))
    ImageDraw.Draw(green).ellipse([0, 0, outer - 1, outer - 1], fill=(*SENKYO_GREEN, 255))

    photo_layer = Image.new("RGBA", (outer, outer), (0, 0, 0, 0))
    # リング側へ 2px 食い込ませてヘアライン隙間を消す
    overlap = 2
    photo_size = size + overlap * 2
    if path and path.exists():
        inner = _make_circle_avatar(path, photo_size, soft_edge=False)
    else:
        inner = Image.new("RGBA", (photo_size, photo_size), (220, 220, 220, 255))
        inner.putalpha(_circle_mask(photo_size, soft=False))
        inner_draw = ImageDraw.Draw(inner)
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        initial_font = load_font(max(40, size // 3), bold=True)
        initial = name[0] if name else "?"
        ib = probe.textbbox((0, 0), initial, font=initial_font)
        iw, ih = ib[2] - ib[0], ib[3] - ib[1]
        inner_draw.text(
            ((photo_size - iw) // 2, (photo_size - ih) // 2 - ib[1]),
            initial,
            fill=(*TEXT_SECONDARY, 255),
            font=initial_font,
        )
    photo_layer.paste(inner, (ring - overlap, ring - overlap), inner)
    return Image.alpha_composite(green, photo_layer)


def _badge_meta_line(plan: VideoPlan) -> str:
    parts = [p for p in (plan.name_reading, plan.age, plan.gender) if p]
    return " / ".join(parts)


def _render_name_badge(plan: VideoPlan, work_dir: Path) -> Path:
    """黄緑塗り（枠なし）＋名前／メタ情報。"""
    wm = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    name_font = load_font(NAME_FONT_SIZE, bold=True)
    meta_font = load_font(META_FONT_SIZE)
    probe = ImageDraw.Draw(wm)
    name_bbox = probe.textbbox((0, 0), plan.watermark, font=name_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]

    meta = _badge_meta_line(plan)
    meta_w = meta_h = 0
    meta_bbox = (0, 0, 0, 0)
    if meta:
        meta_bbox = probe.textbbox((0, 0), meta, font=meta_font)
        meta_w = meta_bbox[2] - meta_bbox[0]
        meta_h = meta_bbox[3] - meta_bbox[1]

    text_block_h = name_h + (8 + meta_h if meta else 0)
    text_block_w = max(name_w, meta_w)

    has_avatar = plan.portrait_path is not None and plan.portrait_path.exists()
    avatar_size = AVATAR_SIZE if has_avatar else 0
    gap = BADGE_GAP if has_avatar else 0

    badge_h = max(avatar_size, text_block_h) + BADGE_PAD_Y * 2
    cap = badge_h // 2
    side_pad = BADGE_SIDE_PAD
    badge_w = side_pad + avatar_size + gap + text_block_w + side_pad
    bx, by = 28, 40

    badge = ImageDraw.Draw(wm)
    badge.rounded_rectangle(
        [bx, by, bx + badge_w, by + badge_h],
        radius=cap,
        fill=(*SENKYO_GREEN, 245),
    )

    if has_avatar:
        avatar = _make_circle_avatar(plan.portrait_path, AVATAR_SIZE)
        ax = bx + side_pad
        ay = by + (badge_h - AVATAR_SIZE) // 2
        wm.paste(avatar, (ax, ay), avatar)
        text_x = ax + AVATAR_SIZE + gap
    else:
        text_x = bx + side_pad

    text_y0 = by + (badge_h - text_block_h) // 2
    name_y = text_y0 - name_bbox[1]
    probe.text((text_x, name_y), plan.watermark, fill=(255, 255, 255, 255), font=name_font)
    if meta:
        meta_y = text_y0 + name_h + 8 - meta_bbox[1]
        probe.text((text_x, meta_y), meta, fill=(255, 255, 255, 230), font=meta_font)

    wm_path = work_dir / "overlay_watermark.png"
    wm.save(wm_path)
    return wm_path


def _render_telop_slide(text: str, index: int, work_dir: Path) -> Path:
    font, lines = _fit_telop_layout(text)
    probe = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(probe)

    metrics = [_telop_line_metrics(draw, line, font) for line in lines]
    line_widths = [m[0] for m in metrics]
    line_heights = [m[1] for m in metrics]
    line_tops = [m[2] for m in metrics]
    text_block_h = sum(line_heights) + TELOP_LINE_GAP * max(len(lines) - 1, 0)
    text_block_w = max(line_widths) if line_widths else 0

    box_w = min(text_block_w + TELOP_PAD_X * 2, TELOP_MAX_WIDTH)
    box_h = text_block_h + TELOP_PAD_Y * 2
    bx = (WIDTH - box_w) // 2
    anchor_y = int(HEIGHT * 0.62)
    by = anchor_y - box_h // 2

    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    badge = ImageDraw.Draw(layer)
    badge.rounded_rectangle(
        [bx, by, bx + box_w, by + box_h],
        radius=14,
        fill=TELOP_BG_FILL,
        outline=(*SENKYO_GREEN, 255),
        width=TELOP_BORDER_WIDTH,
    )

    y = by + TELOP_PAD_Y
    for i, line in enumerate(lines):
        lw, lh, top = metrics[i]
        x = bx + (box_w - lw) // 2
        _draw_telop_line(badge, (x, y - top), line, font, (*TEXT_PRIMARY, 255))
        y += lh + TELOP_LINE_GAP

    out = work_dir / f"overlay_telop_{index:02d}.png"
    layer.save(out)
    return out


def render_page_bg_wash(work_dir: Path) -> Path:
    """選挙ドットコムと同系色の薄い透過レイヤー。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    wash = Image.new("RGBA", (WIDTH, HEIGHT), (*PAGE_BG, PAGE_BG_WASH_ALPHA))
    out = work_dir / "page_bg_wash.png"
    wash.save(out)
    return out


def render_overlays(
    plan: VideoPlan, work_dir: Path
) -> tuple[Path, list[tuple[Path, float, float]]]:
    work_dir.mkdir(parents=True, exist_ok=True)
    wm_path = _render_name_badge(plan, work_dir)

    telop_paths: list[tuple[Path, float, float]] = []
    for slide in plan.telops:
        out = _render_telop_slide(slide.text, slide.index, work_dir)
        telop_paths.append((out, slide.start_sec, slide.end_sec))

    return wm_path, telop_paths


END_CARD_AVATAR_SIZE = 340
END_CARD_AVATAR_RING = 12  # 緑リングの太さ（写真外周にぴったり密着）
END_CARD_NAME_FONT_SIZE = 72
END_CARD_NAME_MAX_WIDTH = 980
END_CARD_STATUS = "情報発信中！"
END_CARD_STATUS_FONT_SIZE = 56
END_CARD_STATUS_MAX_WIDTH = 980
END_CARD_GAP_AVATAR_NAME = 44
END_CARD_GAP_NAME_STATUS = 28
END_CARD_GAP_STATUS_CTA = 48
END_CARD_CTA = "続きは活動記録をチェック"
END_CARD_CTA_FONT_SIZE = 40
END_CARD_CTA_PAD_X = 36
END_CARD_CTA_PAD_Y = 22
END_CARD_DISCLAIMER = "この動画はボネクタの活動記録に基き、AIで生成しています。"
END_CARD_DISCLAIMER_FONT_SIZE = 26
END_CARD_DISCLAIMER_MARGIN_BOTTOM = 72


def _cover_resize(src: Image.Image, tw: int, th: int) -> Image.Image:
    ratio = max(tw / src.width, th / src.height)
    nw = int(src.width * ratio)
    nh = int(src.height * ratio)
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def _build_end_card_background(plan: VideoPlan) -> Image.Image:
    """肖像ぼかし＋サイト色は背景のみ。写真・文字はその上に描く。"""
    if plan.portrait_path and plan.portrait_path.exists():
        portrait = Image.open(plan.portrait_path).convert("RGB")
        portrait = _cover_resize(portrait, WIDTH, HEIGHT)
        portrait = portrait.filter(ImageFilter.GaussianBlur(40))
        portrait = ImageEnhance.Brightness(portrait).enhance(1.12)
        portrait = ImageEnhance.Color(portrait).enhance(0.6)
        base = portrait.convert("RGBA")
    else:
        base = Image.new("RGBA", (WIDTH, HEIGHT), (*PAGE_BG, 255))

    wash = Image.new("RGBA", (WIDTH, HEIGHT), (*PAGE_BG, PAGE_BG_WASH_ALPHA))
    return Image.alpha_composite(base, wash)


def _fit_single_line_font(
    text: str,
    max_size: int,
    max_width: int,
    *,
    bold: bool = False,
    min_size: int = 28,
) -> tuple[ImageFont.ImageFont, tuple[int, int, int, int]]:
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = max_size
    while size >= min_size:
        font = load_font(size, bold=bold)
        bbox = probe.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font, bbox
        size -= 2
    font = load_font(min_size, bold=bold)
    return font, probe.textbbox((0, 0), text, font=font)


def _glyph_ink_center_y(font: ImageFont.ImageFont, text: str) -> float:
    """グリフの実画素から縦方向の光学中心（描画原点からのオフセット）を返す。"""
    mask = font.getmask(text, mode="L")
    w, h = mask.size
    if w <= 0 or h <= 0:
        bb = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
        return (bb[1] + bb[3]) / 2.0
    # ベースセル上端からのインク重心
    weighted = 0.0
    total = 0.0
    # getmask は (0,0) がグリフ原点付近。textbbox の top でキャンバス位置に合わせる
    bb = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    for y in range(h):
        row = 0
        for x in range(w):
            row += mask.getpixel((x, y))
        if row:
            weighted += y * row
            total += row
    if total <= 0:
        return (bb[1] + bb[3]) / 2.0
    # mask 内 y → 描画座標系（textbbox 上端基準）
    return bb[1] + weighted / total


def _draw_cta_chevron(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    cy: float,
    height: int,
    fill: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> int:
    """右向きシェブロンを cy 基準で縦中央に描画。戻り値は右端 x。"""
    h = max(16, height)
    w = max(10, int(h * 0.55))
    thickness = max(3, h // 7)
    # くの字2本線（上下対称で確実に縦中央）
    x0 = left
    x1 = left + w
    y_top = int(round(cy - h / 2))
    y_bot = int(round(cy + h / 2))
    y_mid = int(round(cy))
    draw.line([(x0, y_top), (x1, y_mid)], fill=fill, width=thickness)
    draw.line([(x1, y_mid), (x0, y_bot)], fill=fill, width=thickness)
    return x1


def _draw_cta_label(
    draw: ImageDraw.ImageDraw,
    btn_x: int,
    btn_y: int,
    btn_w: int,
    btn_h: int,
    body: str,
    font: ImageFont.ImageFont,
) -> None:
    """本文＋縦中央揃えのシェブロン（`>` 相当）をボタン内に描画。"""
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    body_bb = probe.textbbox((0, 0), body, font=font)
    body_w = body_bb[2] - body_bb[0]
    body_h = body_bb[3] - body_bb[1]
    gap = 14
    chev_h = max(22, int(body_h * 0.72))
    chev_w = max(10, int(chev_h * 0.55))
    total_w = body_w + gap + chev_w

    x0 = btn_x + (btn_w - total_w) // 2
    body_y = btn_y + (btn_h - body_h) // 2 - body_bb[1]
    body_x = x0 - body_bb[0]
    draw.text((body_x, body_y), body, fill=(255, 255, 255, 255), font=font)

    body_ink_cy = body_y + _glyph_ink_center_y(font, body)
    _draw_cta_chevron(draw, left=body_x + body_w + gap, cy=body_ink_cy, height=chev_h)


def render_end_card_frame(plan: VideoPlan, work_dir: Path) -> Path:
    img = _build_end_card_background(plan).convert("RGBA")
    draw = ImageDraw.Draw(img)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    name = plan.watermark
    avatar_size = END_CARD_AVATAR_SIZE
    ring = END_CARD_AVATAR_RING
    avatar_outer = avatar_size + ring * 2

    name_font, name_bbox = _fit_single_line_font(
        name,
        END_CARD_NAME_FONT_SIZE,
        END_CARD_NAME_MAX_WIDTH,
        bold=True,
        min_size=40,
    )
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]

    status_font, status_bbox = _fit_single_line_font(
        END_CARD_STATUS,
        END_CARD_STATUS_FONT_SIZE,
        END_CARD_STATUS_MAX_WIDTH,
        bold=False,
        min_size=26,
    )
    status_w = status_bbox[2] - status_bbox[0]
    status_h = status_bbox[3] - status_bbox[1]

    cta_font = load_font(END_CARD_CTA_FONT_SIZE, bold=True)
    body_bb = probe.textbbox((0, 0), END_CARD_CTA, font=cta_font)
    body_w = body_bb[2] - body_bb[0]
    cth = body_bb[3] - body_bb[1]
    chev_h = max(22, int(cth * 0.72))
    chev_w = max(10, int(chev_h * 0.55))
    ctw = body_w + 14 + chev_w
    cta_btn_w = ctw + END_CARD_CTA_PAD_X * 2
    cta_btn_h = max(cth + END_CARD_CTA_PAD_Y * 2, 72)
    cta_radius = cta_btn_h // 2

    block_h = (
        avatar_outer
        + END_CARD_GAP_AVATAR_NAME
        + name_h
        + END_CARD_GAP_NAME_STATUS
        + status_h
        + END_CARD_GAP_STATUS_CTA
        + cta_btn_h
    )
    y0 = HEIGHT // 2 - block_h // 2

    ringed = _make_ringed_avatar(plan.portrait_path, avatar_size, ring, name)
    ax = (WIDTH - avatar_outer) // 2
    img.paste(ringed, (ax, y0), ringed)
    avatar_bottom = y0 + avatar_outer

    name_x = (WIDTH - name_w) // 2
    name_y = avatar_bottom + END_CARD_GAP_AVATAR_NAME - name_bbox[1]
    draw.text((name_x, name_y), name, fill=(*TEXT_PRIMARY, 255), font=name_font)

    status_x = (WIDTH - status_w) // 2
    status_y = name_y + name_bbox[3] + END_CARD_GAP_NAME_STATUS - status_bbox[1]
    draw.text((status_x, status_y), END_CARD_STATUS, fill=(*TEXT_PRIMARY, 255), font=status_font)

    cta_btn_x = (WIDTH - cta_btn_w) // 2
    cta_btn_y = status_y + status_bbox[3] + END_CARD_GAP_STATUS_CTA

    draw.rounded_rectangle(
        [cta_btn_x, cta_btn_y, cta_btn_x + cta_btn_w, cta_btn_y + cta_btn_h],
        radius=cta_radius,
        fill=(*SENKYO_GREEN, 255),
    )
    draw.rounded_rectangle(
        [cta_btn_x, cta_btn_y, cta_btn_x + cta_btn_w, cta_btn_y + cta_btn_h],
        radius=cta_radius,
        outline=(*SENKYO_GREEN_DARK, 255),
        width=2,
    )

    _draw_cta_label(
        draw,
        cta_btn_x,
        cta_btn_y,
        cta_btn_w,
        cta_btn_h,
        END_CARD_CTA,
        cta_font,
    )

    disclaimer_font = load_font(END_CARD_DISCLAIMER_FONT_SIZE)
    db = probe.textbbox((0, 0), END_CARD_DISCLAIMER, font=disclaimer_font)
    dw = db[2] - db[0]
    dh = db[3] - db[1]
    dx = (WIDTH - dw) // 2
    dy = HEIGHT - END_CARD_DISCLAIMER_MARGIN_BOTTOM - dh - db[1]
    draw.text((dx, dy), END_CARD_DISCLAIMER, fill=(*TEXT_SECONDARY, 220), font=disclaimer_font)

    out = work_dir / "end_card_frame.png"
    img.save(out)
    return out
