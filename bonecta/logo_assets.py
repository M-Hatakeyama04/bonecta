from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from bonecta.paths import LOGO_PNG_PATH, LOGO_SVG_PATH

WIDTH = 1080
HEIGHT = 1920
CORNER_LOGO_MAX_WIDTH = 400
CORNER_LOGO_MAX_HEIGHT = 120
CORNER_LOGO_MARGIN = 32
END_CARD_LOGO_HEIGHT = 72


def find_logo_source() -> Path | None:
    if LOGO_PNG_PATH.exists():
        return LOGO_PNG_PATH
    if LOGO_SVG_PATH.exists():
        return LOGO_SVG_PATH
    return None


def _strip_red_background(img: Image.Image) -> Image.Image:
    """旧プレースホルダーの赤角丸背景のみ除去（黒文字ロゴは保持）"""
    img = img.convert("RGBA")
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            if a < 128:
                continue
            if r > 140 and g < 100 and b < 100 and r > g + 30 and r > b + 30:
                pixels[x, y] = (0, 0, 0, 0)
    return img


def _trim_logo_content(img: Image.Image) -> Image.Image:
    img = _strip_red_background(img.convert("RGBA"))
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def _rasterize_svg(path: Path, render_width: int) -> Image.Image:
    import platform

    if platform.system() == "Darwin":
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = subprocess.run(
                ["qlmanage", "-t", "-s", str(render_width * 2), "-o", str(out_dir), str(path.resolve())],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                png = next(out_dir.glob(f"{path.name}*.png"), None)
                if png is not None:
                    return Image.open(png).convert("RGBA")

    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM

        drawing = svg2rlg(str(path))
        if drawing is None:
            raise ValueError("SVG parse failed")
        scale = render_width / max(drawing.width, 1)
        drawing.width = render_width
        drawing.height = drawing.height * scale
        drawing.scale(scale, scale)
        png_bytes = renderPM.drawToString(drawing, fmt="PNG")
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except ImportError:
        pass

    raise RuntimeError(
        "SVG を読み込めません。img/logo.png（透過PNG）を img/ に置いてください。"
    )


def load_logo_image(
    max_width: int = CORNER_LOGO_MAX_WIDTH,
    max_height: int = CORNER_LOGO_MAX_HEIGHT,
) -> Image.Image | None:
    source = find_logo_source()
    if source is None:
        return None

    if source.suffix.lower() == ".svg":
        logo = _rasterize_svg(source, max_width * 2)
    else:
        logo = Image.open(source).convert("RGBA")

    logo = _trim_logo_content(logo)
    if logo.getbbox() is None:
        return None

    ratio = min(max_width / logo.width, max_height / logo.height)
    nw = max(1, int(logo.width * ratio))
    nh = max(1, int(logo.height * ratio))
    return logo.resize((nw, nh), Image.Resampling.LANCZOS)


def prepare_corner_logo_asset(
    work_dir: Path,
    max_width: int = CORNER_LOGO_MAX_WIDTH,
    max_height: int = CORNER_LOGO_MAX_HEIGHT,
) -> Path | None:
    logo = load_logo_image(max_width=max_width, max_height=max_height)
    if logo is None:
        return None
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / "corner_logo_asset.png"
    logo.save(out)
    return out
