from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MEDIA_DIR = ROOT / "data" / "media"


def _draw_label(draw: ImageDraw.ImageDraw, text: str, size: tuple[int, int]) -> None:
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.rectangle([0, 0, size[0], 80], fill=(0, 0, 0, 180))
    draw.text((24, 16), text, fill=(255, 255, 255), font=font)


def create_sample_media() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # 画像A: 横長 16:9
    img_a = Image.new("RGB", (1920, 1080), (180, 40, 40))
    d = ImageDraw.Draw(img_a)
    _draw_label(d, "Photo A - 秋祭りの櫓と人混み (16:9)", (1920, 1080))
    d.rectangle([760, 300, 1160, 900], outline=(255, 220, 100), width=8)
    img_a.save(MEDIA_DIR / "photo_a_wide.jpg", quality=90)

    # 画像B: 縦長 9:16
    img_b = Image.new("RGB", (1080, 1920), (40, 90, 160))
    d = ImageDraw.Draw(img_b)
    _draw_label(d, "Photo B - 神輿担ぎ自撮り (9:16)", (1080, 1920))
    d.ellipse([340, 700, 740, 1100], outline=(255, 255, 255), width=6)
    img_b.save(MEDIA_DIR / "photo_b_tall.jpg", quality=90)

    # 画像C: 横長・小さい
    img_c = Image.new("RGB", (640, 360), (60, 140, 80))
    d = ImageDraw.Draw(img_c)
    _draw_label(d, "Photo C - 握手 (small 16:9)", (640, 360))
    img_c.save(MEDIA_DIR / "photo_c_small.jpg", quality=90)

    # 動画D: ffmpeg で横長30秒生成（後で音声追加）
    silent = MEDIA_DIR / "video_d_speech_silent.mp4"
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=30",
            "-t",
            "30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(MEDIA_DIR / "video_d_speech.mp4"),
        ],
        check=True,
        capture_output=True,
    )

    manifest = {
        "photo_a_wide.jpg": {"orientation": "landscape", "width": 1920, "height": 1080},
        "photo_b_tall.jpg": {"orientation": "portrait", "width": 1080, "height": 1920},
        "photo_c_small.jpg": {"orientation": "landscape", "width": 640, "height": 360, "size_tier": "small"},
        "video_d_speech.mp4": {"orientation": "landscape", "duration_sec": 30, "has_audio": True},
    }
    (MEDIA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Sample media created in {MEDIA_DIR}")


if __name__ == "__main__":
    create_sample_media()
