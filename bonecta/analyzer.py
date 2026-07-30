from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from bonecta.models import (
    BlogPattern,
    BlogPost,
    MediaAsset,
    MediaKind,
    Orientation,
    PoliticianInfo,
    SizeTier,
    SourceStatus,
)

# 過激・誹謗中傷の簡易検出（本番は LLM + モデレーション API 推奨）
BLOCK_KEYWORDS = (
    "死ね",
    "クズ",
    "消えろ",
    "嘘つき",
    "犯罪者",
    "恥を知れ",
)


def detect_blog_pattern(media: list[MediaAsset]) -> BlogPattern:
    """メディア構成から go2senkyo 系の代表パターンを推定する。"""
    images = [m for m in media if m.is_image and m.is_usable]
    videos = [m for m in media if m.is_video and m.is_usable]
    embeds = [m for m in media if m.kind == MediaKind.EMBED_THUMBNAIL and m.is_usable]

    has_broken_embed = any(
        m.kind == MediaKind.EMBED_THUMBNAIL and m.source_status == SourceStatus.BROKEN
        for m in media
    )
    if has_broken_embed and not any(m.is_usable for m in media):
        return BlogPattern.VIDEO_BROKEN

    if not images and not videos and not embeds:
        thumbs = [m for m in media if m.kind == MediaKind.THUMBNAIL]
        return (
            BlogPattern.NO_IMAGES_WITH_THUMB
            if thumbs
            else BlogPattern.NO_IMAGES_NO_THUMB
        )

    if embeds and images:
        e_portrait = any(
            e.orientation == Orientation.PORTRAIT or e.embed_platform == "youtube"
            for e in embeds
        )
        if any(i.orientation == Orientation.LANDSCAPE for i in images) and e_portrait:
            return BlogPattern.MIXED_LANDSCAPE_VIDEO_PORTRAIT
        return BlogPattern.MIXED_YOUTUBE_AND_IMAGES

    if embeds and not images:
        if any(e.embed_platform == "youtube" and e.orientation == Orientation.PORTRAIT for e in embeds):
            return BlogPattern.VIDEO_YOUTUBE_SHORT
        if embeds:
            return BlogPattern.VIDEO_YOUTUBE_LANDSCAPE

    if videos and images:
        v_portrait = any(v.orientation == Orientation.PORTRAIT for v in videos)
        v_landscape = any(v.orientation == Orientation.LANDSCAPE for v in videos)
        i_portrait = any(i.orientation == Orientation.PORTRAIT for i in images)
        if v_portrait and any(i.orientation == Orientation.LANDSCAPE for i in images):
            return BlogPattern.MIXED_LANDSCAPE_VIDEO_PORTRAIT
        return BlogPattern.MIXED_YOUTUBE_AND_IMAGES

    if videos and not images:
        if any(v.orientation == Orientation.PORTRAIT for v in videos):
            return BlogPattern.VIDEO_PORTRAIT
        return BlogPattern.VIDEO_YOUTUBE_LANDSCAPE

    if not videos and images:
        orientations = {i.orientation for i in images}
        has_small = any(i.size_tier == SizeTier.SMALL for i in images)
        if Orientation.PORTRAIT in orientations and Orientation.LANDSCAPE in orientations:
            return BlogPattern.IMAGES_MIXED
        if orientations == {Orientation.PORTRAIT}:
            return (
                BlogPattern.IMAGES_PORTRAIT_SMALL
                if has_small
                else BlogPattern.IMAGES_PORTRAIT
            )
        if has_small:
            return BlogPattern.IMAGES_LANDSCAPE_SMALL
        return BlogPattern.IMAGES_LANDSCAPE

    return BlogPattern.SPECIAL_EMBED


def classify_orientation(width: int | None, height: int | None) -> Orientation:
    if not width or not height:
        return Orientation.UNKNOWN
    ratio = width / height
    if ratio > 1.15:
        return Orientation.LANDSCAPE
    if ratio < 0.87:
        return Orientation.PORTRAIT
    return Orientation.SQUARE


def classify_size_tier(width: int | None, height: int | None) -> SizeTier:
    if not width or not height:
        return SizeTier.NORMAL
    if max(width, height) < 720:
        return SizeTier.SMALL
    return SizeTier.NORMAL


def check_content_safety(text: str) -> tuple[bool, str]:
    lowered = text.lower()
    for kw in BLOCK_KEYWORDS:
        if kw in text or kw in lowered:
            return False, f"不適切な表現を検出: {kw}"
    return True, ""


def parse_blog_post(
    text: str,
    politician: PoliticianInfo,
    media_specs: Iterable[dict],
    local_media_dir: Path | None = None,
) -> BlogPost:
    """ブログ素材仕様を MediaAsset リストに変換する。"""
    assets: list[MediaAsset] = []
    for spec in media_specs:
        asset_id = spec["id"]
        kind = MediaKind(spec.get("kind", "image"))
        url = spec.get("url", "")
        local_name = spec.get("local_file")
        local_path = None
        if local_media_dir and local_name:
            candidate = local_media_dir / local_name
            if candidate.exists():
                local_path = candidate

        orientation = Orientation(spec["orientation"]) if "orientation" in spec else Orientation.UNKNOWN
        size_tier = SizeTier(spec["size_tier"]) if "size_tier" in spec else SizeTier.NORMAL
        status = SourceStatus(spec.get("status", "available"))

        if local_path and local_path.exists():
            status = SourceStatus.AVAILABLE
            try:
                from PIL import Image

                if kind in (MediaKind.IMAGE, MediaKind.THUMBNAIL, MediaKind.EMBED_THUMBNAIL):
                    with Image.open(local_path) as img:
                        w, h = img.size
                        orientation = classify_orientation(w, h)
                        size_tier = classify_size_tier(w, h)
            except Exception:
                pass

        assets.append(
            MediaAsset(
                id=asset_id,
                kind=kind,
                url=url,
                local_path=local_path,
                orientation=orientation,
                size_tier=size_tier,
                duration_sec=spec.get("duration_sec"),
                has_audio=spec.get("has_audio", False),
                source_status=status,
                width=spec.get("width"),
                height=spec.get("height"),
                embed_platform=spec.get("embed_platform"),
            )
        )

    post = BlogPost(text=text, politician=politician, media=assets)
    post.pattern = detect_blog_pattern(assets)
    return post


def summarize_district_label(district: str) -> str:
    """東京第1区 → 東京1区"""
    return re.sub(r"第(\d+)区", r"\1区", district)
