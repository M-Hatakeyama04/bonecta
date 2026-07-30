from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class MediaKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    YOUTUBE_EMBED = "youtube_embed"
    EMBED_THUMBNAIL = "embed_thumbnail"
    THUMBNAIL = "thumbnail"
    END_CARD = "end_card"
    NONE = "none"


class Orientation(str, Enum):
    LANDSCAPE = "landscape"  # 16:9 等
    PORTRAIT = "portrait"  # 9:16 等
    SQUARE = "square"
    UNKNOWN = "unknown"


class SizeTier(str, Enum):
    NORMAL = "normal"
    SMALL = "small"


class SourceStatus(str, Enum):
    AVAILABLE = "available"
    BROKEN = "broken"
    PENDING = "pending"


class BlogPattern(str, Enum):
    """go2senkyo.com で観測される代表的パターン（分類用）"""

    IMAGES_LANDSCAPE = "images_landscape"
    IMAGES_LANDSCAPE_SMALL = "images_landscape_small"
    IMAGES_PORTRAIT = "images_portrait"
    IMAGES_MIXED = "images_mixed"
    IMAGES_PORTRAIT_SMALL = "images_portrait_small"
    NO_IMAGES_WITH_THUMB = "no_images_with_thumb"
    NO_IMAGES_NO_THUMB = "no_images_no_thumb"
    VIDEO_YOUTUBE_LANDSCAPE = "video_youtube_landscape"
    VIDEO_YOUTUBE_SHORT = "video_youtube_short"
    VIDEO_PORTRAIT = "video_portrait"
    VIDEO_BROKEN = "video_broken"
    MIXED_LANDSCAPE_VIDEO_PORTRAIT = "mixed_landscape_video_portrait"
    MIXED_YOUTUBE_AND_IMAGES = "mixed_youtube_and_images"
    SPECIAL_EMBED = "special_embed"


@dataclass
class PoliticianInfo:
    name: str
    name_reading: str = ""
    district: str = ""
    party: str = ""
    party_color: str = "#E60012"  # 自民党赤
    age: str = ""  # 例: 51歳
    gender: str = ""  # 例: 女性


@dataclass
class MediaAsset:
    id: str
    kind: MediaKind
    url: str = ""
    local_path: Optional[Path] = None
    orientation: Orientation = Orientation.UNKNOWN
    size_tier: SizeTier = SizeTier.NORMAL
    duration_sec: Optional[float] = None
    has_audio: bool = False
    source_status: SourceStatus = SourceStatus.PENDING
    width: Optional[int] = None
    height: Optional[int] = None
    embed_platform: Optional[str] = None  # youtube | facebook | instagram

    @property
    def is_usable(self) -> bool:
        if self.source_status == SourceStatus.BROKEN:
            return False
        if self.kind in (MediaKind.IMAGE, MediaKind.VIDEO, MediaKind.THUMBNAIL, MediaKind.EMBED_THUMBNAIL):
            return self.local_path is not None and self.local_path.exists()
        return False

    @property
    def is_video(self) -> bool:
        return self.kind == MediaKind.VIDEO

    @property
    def is_image(self) -> bool:
        return self.kind in (MediaKind.IMAGE, MediaKind.THUMBNAIL, MediaKind.EMBED_THUMBNAIL)

    @property
    def needs_blur_background(self) -> bool:
        # YouTubeサムネは縦でも横でもカバー切り抜きせず、横幅まるごと見せる
        if self.kind == MediaKind.EMBED_THUMBNAIL and (self.embed_platform or "").lower() == "youtube":
            return True
        return self.orientation == Orientation.LANDSCAPE or self.size_tier == SizeTier.SMALL


@dataclass
class BlogPost:
    text: str
    politician: PoliticianInfo
    media: list[MediaAsset] = field(default_factory=list)
    pattern: Optional[BlogPattern] = None
    portrait_path: Optional[Path] = None


@dataclass
class TelopSlide:
    index: int
    text: str
    start_sec: float
    end_sec: float


@dataclass
class TimelineSegment:
    asset: MediaAsset
    start_sec: float
    end_sec: float
    fade_in: float = 0.5
    fade_out: float = 0.5
    transition_zoom: bool = False  # 複数枚切替時のみ、冒頭0.5秒でズーム
    blur_bg_motion: str = "none"  # none | pan | rotate（1枚・ボケ背景時）
    crop_preset: str = "default"  # default | wide | close | left | right

    @property
    def duration(self) -> float:
        return self.end_sec - self.start_sec


@dataclass
class VideoPlan:
    segments: list[TimelineSegment]
    telops: list[TelopSlide]
    total_duration: float
    watermark: str
    party_color: str
    portrait_path: Optional[Path] = None
    bgm_path: Optional[Path] = None
    has_video_audio: bool = False
    content_duration: float = 0.0
    end_card_duration: float = 3.0
    tone: str = "positive"
    blocked: bool = False
    block_reason: str = ""
    name_reading: str = ""
    age: str = ""
    gender: str = ""
