from __future__ import annotations

import base64
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image

from bonecta.analyzer import classify_orientation, classify_size_tier
from bonecta.embed_thumbnails import resolve_youtube_thumbnail
from bonecta.models import Orientation
from bonecta.scraper import ScrapedMedia, ScrapedPost

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _resolve_url(url: str) -> str:
    if url.startswith("data:"):
        try:
            payload = url.split(",", 1)[1]
            decoded = base64.b64decode(payload).decode("utf-8").strip()
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass
    return url


def _download_file(url: str, dest: Path) -> bool:
    url = _resolve_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
        return dest.stat().st_size > 0
    except Exception:
        return False


def _image_spec_from_file(local: Path, spec: dict) -> dict:
    try:
        with Image.open(local) as img:
            w, h = img.size
            spec["width"] = w
            spec["height"] = h
            spec["orientation"] = classify_orientation(w, h).value
            spec["size_tier"] = classify_size_tier(w, h).value
    except Exception:
        spec["orientation"] = "unknown"
    spec["local_file"] = local.name
    spec["status"] = "available"
    return spec


def _probe_video(local: Path) -> dict:
    info: dict = {}
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=width,height,codec_type",
                "-of",
                "json",
                str(local),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return info
        data = json.loads(result.stdout or "{}")
        dur = data.get("format", {}).get("duration")
        if dur is not None:
            info["duration_sec"] = float(dur)
        has_audio = False
        w = h = None
        for stream in data.get("streams") or []:
            if stream.get("codec_type") == "audio":
                has_audio = True
            if stream.get("codec_type") == "video":
                w = stream.get("width") or w
                h = stream.get("height") or h
        info["has_audio"] = has_audio
        if w and h:
            info["width"] = int(w)
            info["height"] = int(h)
            info["orientation"] = classify_orientation(int(w), int(h)).value
            info["size_tier"] = classify_size_tier(int(w), int(h)).value
    except Exception:
        pass
    return info


def download_politician_portrait(post: ScrapedPost, media_dir: Path) -> Path | None:
    if not post.portrait_url:
        return None
    local = media_dir / "politician_portrait.jpg"
    if not _download_file(post.portrait_url, local):
        return None
    try:
        with Image.open(local) as img:
            img.verify()
        return local
    except Exception:
        local.unlink(missing_ok=True)
        return None


def _portrait_spec(
    item: ScrapedMedia,
    media_dir: Path,
    portrait_path: Path | None,
) -> dict:
    """政治家画像を埋め込み代替として使う。"""
    spec: dict = {
        "id": item.id,
        "kind": "embed_thumbnail",
        "url": item.url,
        "embed_platform": item.embed_platform,
        "is_live": bool(getattr(item, "is_live", False)),
    }
    local = media_dir / f"{item.id}_portrait.jpg"
    if portrait_path and portrait_path.exists():
        shutil.copy2(portrait_path, local)
        return _image_spec_from_file(local, spec)
    spec["status"] = "broken"
    return spec


def _youtube_thumbnail_spec(item: ScrapedMedia, media_dir: Path, portrait_path: Path | None) -> dict:
    """通常の YouTube → 公式サムネ。取れなければポートレート。"""
    spec: dict = {
        "id": item.id,
        "kind": "embed_thumbnail",
        "url": item.url,
        "embed_platform": "youtube",
        "is_live": False,
    }
    thumb_url = resolve_youtube_thumbnail(item.url, video_id=item.video_id or None)
    if thumb_url:
        local = media_dir / f"{item.id}_thumb.jpg"
        if _download_file(thumb_url, local):
            spec = _image_spec_from_file(local, spec)
            if item.is_short and spec.get("orientation") == Orientation.LANDSCAPE.value:
                # Shorts は正方形寄りサムネでも縦扱いしたい場合あり。実寸を優先。
                pass
            return spec
    return _portrait_spec(item, media_dir, portrait_path)


def _fetch_embed(item: ScrapedMedia, media_dir: Path, portrait_path: Path | None) -> dict:
    """
    埋め込みの表示ルール:
    - YouTube（通常）→ サムネイル
    - YouTube Live / Facebook / Instagram → 政治家画像
    """
    platform = (item.embed_platform or "").lower()
    if platform == "youtube" and not getattr(item, "is_live", False):
        return _youtube_thumbnail_spec(item, media_dir, portrait_path)
    return _portrait_spec(item, media_dir, portrait_path)


def fetch_media_for_post(post: ScrapedPost, media_dir: Path) -> tuple[list[dict], Path | None]:
    """
    素材取得ルール:
    - 画像 → 画像
    - 直接動画ファイル → mp4
    - YouTube → サムネ（Live は政治家画像）
    - Facebook / Instagram → 政治家画像
    - 何もなければ政治家画像フォールバック
    """
    media_dir.mkdir(parents=True, exist_ok=True)
    portrait_path = download_politician_portrait(post, media_dir)
    specs: list[dict] = []
    has_embed = any(m.kind == "embed_thumbnail" for m in post.media)
    has_direct_video = any(m.kind == "video" for m in post.media)

    for item in post.media:
        if item.kind == "embed_thumbnail":
            specs.append(_fetch_embed(item, media_dir, portrait_path))
            continue

        spec: dict = {"id": item.id, "kind": item.kind, "url": item.url}

        # 埋め込みがある記事の OG サムネは YouTube サムネと重複しやすいのでスキップ
        if item.kind == "thumbnail" and item.id == "thumb_og" and has_embed:
            continue

        if item.kind in ("image", "thumbnail"):
            # 直接動画がある記事では画像は本編に使わない（取得自体はしてもよいが、帯域節約でスキップ可）
            # 解析用に残す必要はない → スキップ
            if has_direct_video:
                continue
            ext = ".jpg"
            if ".png" in item.url.lower():
                ext = ".png"
            elif ".webp" in item.url.lower():
                ext = ".webp"
            local = media_dir / f"{item.id}{ext}"
            if not _download_file(item.url, local):
                spec["status"] = "broken"
                specs.append(spec)
                continue
            specs.append(_image_spec_from_file(local, spec))
            continue

        if item.kind == "video":
            local = media_dir / f"{item.id}.mp4"
            ok = local.exists() and local.stat().st_size > 1024
            if not ok:
                ok = _download_file(item.url, local) and local.stat().st_size > 1024
            if ok:
                spec["local_file"] = local.name
                spec["status"] = "available"
                spec.update(_probe_video(local))
                specs.append(spec)
            else:
                spec["status"] = "broken"
                specs.append(spec)

    if not any(s.get("status") == "available" for s in specs) and portrait_path and portrait_path.exists():
        local = media_dir / "portrait_fallback.jpg"
        shutil.copy2(portrait_path, local)
        specs.append(
            _image_spec_from_file(
                local,
                {
                    "id": "portrait_fallback",
                    "kind": "thumbnail",
                    "url": post.portrait_url,
                },
            )
        )

    return specs, portrait_path
