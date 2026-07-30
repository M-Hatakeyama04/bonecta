from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

YOUTUBE_ID_PATTERNS = (
    re.compile(r"youtube\.com/embed/([A-Za-z0-9_-]+)"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]+)"),
    re.compile(r"youtube\.com/watch\?v=([A-Za-z0-9_-]+)"),
    re.compile(r"youtube\.com/shorts/([A-Za-z0-9_-]+)"),
)


def extract_youtube_video_id(url: str) -> Optional[str]:
    for pat in YOUTUBE_ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def _head_ok(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            size = int(resp.headers.get("Content-Length", 0) or 0)
            return resp.status == 200 and size > 1000
    except Exception:
        return False


def _get_json(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def youtube_thumbnail_candidates(video_id: str) -> list[str]:
    return [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    ]


def resolve_youtube_thumbnail(url: str, video_id: Optional[str] = None) -> Optional[str]:
    vid = video_id or extract_youtube_video_id(url)
    if not vid:
        return None

    for candidate in youtube_thumbnail_candidates(vid):
        if _head_ok(candidate):
            return candidate

    oembed = _get_json(f"https://noembed.com/embed?url={urllib.parse.quote(url, safe='')}")
    if oembed and oembed.get("thumbnail_url"):
        return oembed["thumbnail_url"]
    return None


def _og_image_from_html(html: str) -> Optional[str]:
    for pat in (
        r'property="og:image" content="([^"]+)"',
        r"property='og:image' content='([^']+)'",
        r'name="twitter:image" content="([^"]+)"',
    ):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def resolve_facebook_thumbnail(url: str) -> Optional[str]:
    oembed = _get_json(
        "https://noembed.com/embed?url=" + urllib.parse.quote(url, safe="")
    )
    if oembed and oembed.get("thumbnail_url"):
        return oembed["thumbnail_url"]

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
        thumb = _og_image_from_html(resp.text)
        if thumb:
            return thumb
    except Exception:
        pass
    return None


def resolve_instagram_thumbnail(url: str) -> Optional[str]:
    oembed = _get_json(
        "https://noembed.com/embed?url=" + urllib.parse.quote(url, safe="")
    )
    if oembed and oembed.get("thumbnail_url"):
        return oembed["thumbnail_url"]

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
        thumb = _og_image_from_html(resp.text)
        if thumb and "instagram" in thumb:
            return thumb
    except Exception:
        pass
    return None


def resolve_embed_thumbnail(platform: str, url: str, video_id: Optional[str] = None) -> Optional[str]:
    if platform == "youtube":
        return resolve_youtube_thumbnail(url, video_id=video_id)
    if platform == "facebook":
        return resolve_facebook_thumbnail(url)
    if platform == "instagram":
        return resolve_instagram_thumbnail(url)
    return None
