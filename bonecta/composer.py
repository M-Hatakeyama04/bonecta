from __future__ import annotations

from bonecta.analyzer import check_content_safety
from bonecta.bgm import pick_random_bgm
from bonecta.models import (
    BlogPost,
    MediaAsset,
    MediaKind,
    TimelineSegment,
    VideoPlan,
)
from bonecta.telop import TELOP_SLIDE_DURATION, generate_telop_slides

TARGET_DURATION = 20.0
END_CARD_DURATION = 3.0
CROSSFADE = 0.5
MAX_VIDEO_USE = 15.0
MAX_IMAGES = 5
MAX_TELOP_CONTENT = 20.0  # 5枚×4秒


def _usable_assets(post: BlogPost) -> tuple[list[MediaAsset], list[MediaAsset]]:
    """直接動画ファイルと、画像系（ブログ画像・サムネ・埋め込み静止画）。"""
    videos = [m for m in post.media if m.kind == MediaKind.VIDEO and m.is_usable]
    images = [m for m in post.media if m.is_image and m.is_usable]
    return videos, images


def _is_blog_image(asset: MediaAsset) -> bool:
    return asset.kind == MediaKind.IMAGE


def _build_video_allocations(
    videos: list[MediaAsset],
    target: float = TARGET_DURATION,
) -> list[tuple[MediaAsset, float]]:
    """直接動画のみ本編に使う（画像との混在時も動画優先）。"""
    vid = videos[0]
    budget = min(MAX_VIDEO_USE, target)
    if vid.duration_sec and vid.duration_sec > 0:
        budget = min(budget, max(float(vid.duration_sec), 6.0))
    return [(vid, budget)]


def _build_image_allocations(
    images: list[MediaAsset],
    target: float = TARGET_DURATION,
) -> list[tuple[MediaAsset, float]]:
    selected = images[:MAX_IMAGES]
    if not selected:
        placeholder = MediaAsset(id="fallback", kind=MediaKind.NONE)
        return [(placeholder, target)]
    n = len(selected)
    overlap = max(n - 1, 0) * CROSSFADE
    budget = target + overlap
    per = budget / n
    return [(asset, per) for asset in selected]


def _build_telop_synced_allocations(
    images: list[MediaAsset],
    num_slides: int,
) -> list[tuple[MediaAsset, float, str]]:
    """画像割当。複数枚は等分・周回なし。1枚ブログ画像は中央で寄り。サムネのみは最初から寄り。"""
    selected = images[:MAX_IMAGES]
    total = num_slides * TELOP_SLIDE_DURATION

    if not selected:
        placeholder = MediaAsset(id="fallback", kind=MediaKind.NONE)
        return [(placeholder, total, "default")]

    if len(selected) == 1:
        asset = selected[0]
        if _is_blog_image(asset):
            half = total / 2
            return [
                (asset, half, "wide"),
                (asset, half, "close"),
            ]
        # YouTubeサムネは横幅を切らず全幅表示。その他（政治家画像等）は寄り。
        if (
            asset.kind == MediaKind.EMBED_THUMBNAIL
            and (asset.embed_platform or "").lower() == "youtube"
        ):
            return [(asset, total, "default")]
        return [(asset, total, "close")]

    per = total / len(selected)
    return [(asset, per, "default") for asset in selected]


def _content_slide_count(blog_text: str, target: float = MAX_TELOP_CONTENT) -> int:
    from bonecta.telop import MAX_SLIDES, _rule_based_telops

    max_fit = max(1, int(target // TELOP_SLIDE_DURATION))
    slides_text = _rule_based_telops(blog_text)[: min(MAX_SLIDES, max_fit)]
    return max(1, len(slides_text))


def build_video_plan(post: BlogPost) -> VideoPlan:
    """
    表示ルール:
    - 直接動画あり（画像の有無問わず）→ 動画表示・テロップなし
    - それ以外で画像系あり（ブログ画像 / YouTubeサムネ / FB・IG・Liveの政治家画像）→ 画像表示・テロップあり
    - 何もなければフォールバック（政治家画像）・テロップあり
    """
    safe, reason = check_content_safety(post.text)
    watermark = post.politician.name

    if not safe:
        return VideoPlan(
            segments=[],
            telops=[],
            total_duration=5.0,
            watermark=watermark,
            party_color=post.politician.party_color,
            portrait_path=post.portrait_path,
            blocked=True,
            block_reason=reason,
            name_reading=post.politician.name_reading,
            age=post.politician.age,
            gender=post.politician.gender,
        )

    videos, images = _usable_assets(post)
    slide_count = _content_slide_count(post.text)
    telop_content_duration = slide_count * TELOP_SLIDE_DURATION

    enable_telops = True
    if videos:
        # 動画のみ / 画像+動画 → 動画優先・テロップなし
        allocations = _build_video_allocations(videos)
        crop_presets = ["default"] * len(allocations)
        enable_telops = False
        content_duration = max(8.0, min(MAX_VIDEO_USE, sum(d for _, d in allocations)))
    else:
        # 画像のみ / YouTubeサムネ / 政治家画像 / なしフォールバック → テロップあり
        synced = _build_telop_synced_allocations(images, slide_count)
        allocations = [(asset, dur) for asset, dur, _ in synced]
        crop_presets = [preset for _, _, preset in synced]
        telop_content_duration = min(MAX_TELOP_CONTENT, telop_content_duration)
        content_duration = telop_content_duration

    segments: list[TimelineSegment] = []
    cursor = 0.0
    for i, (asset, dur) in enumerate(allocations):
        fade_in = CROSSFADE if i > 0 else 0.0
        fade_out = CROSSFADE
        visible = dur if enable_telops else max(dur - fade_out, 0.5)
        end = cursor + visible
        segments.append(
            TimelineSegment(
                asset=asset,
                start_sec=cursor,
                end_sec=end,
                fade_in=fade_in,
                fade_out=fade_out,
                transition_zoom=False,
                crop_preset=crop_presets[i] if i < len(crop_presets) else "default",
            )
        )
        cursor = end

    if not enable_telops:
        content_duration = cursor

    has_video_audio = any(a.kind == MediaKind.VIDEO and a.has_audio for a, _ in allocations)

    end_asset = MediaAsset(id="end_card", kind=MediaKind.END_CARD)
    segments.append(
        TimelineSegment(
            asset=end_asset,
            start_sec=cursor,
            end_sec=cursor + END_CARD_DURATION - CROSSFADE,
            fade_in=CROSSFADE,
            fade_out=0.0,
        )
    )

    total_duration = content_duration + END_CARD_DURATION - CROSSFADE
    telops = (
        generate_telop_slides(post.text, content_duration, len(allocations))
        if enable_telops
        else []
    )

    return VideoPlan(
        segments=segments,
        telops=telops,
        total_duration=total_duration,
        content_duration=content_duration,
        end_card_duration=END_CARD_DURATION,
        watermark=watermark,
        party_color=post.politician.party_color,
        portrait_path=post.portrait_path,
        bgm_path=pick_random_bgm(),
        has_video_audio=has_video_audio,
        tone="元気・お祭り・感謝",
        name_reading=post.politician.name_reading,
        age=post.politician.age,
        gender=post.politician.gender,
    )
