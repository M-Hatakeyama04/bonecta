from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from bonecta.models import PoliticianInfo

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

YOUTUBE_PATTERNS = (
    re.compile(r"youtube\.com/embed/([A-Za-z0-9_-]+)"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]+)"),
    re.compile(r"youtube\.com/watch\?v=([A-Za-z0-9_-]+)"),
    re.compile(r"youtube\.com/shorts/([A-Za-z0-9_-]+)"),
)


@dataclass
class ScrapedMedia:
    id: str
    kind: str  # image | embed_thumbnail | thumbnail | video
    url: str
    embed_platform: str = ""  # youtube | facebook | instagram
    video_id: str = ""
    is_short: bool = False
    is_live: bool = False


@dataclass
class ScrapedPost:
    source_url: str
    post_id: str
    title: str
    text: str
    politician: PoliticianInfo
    media: list[ScrapedMedia] = field(default_factory=list)
    portrait_url: str = ""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _extract_post_id(url: str) -> str:
    m = re.search(r"/posts/(\d+)", url)
    return m.group(1) if m else urlparse(url).path.replace("/", "_")


def _clean_text(element) -> str:
    for br in element.find_all("br"):
        br.replace_with("\n")
    text = element.get_text("\n", strip=True)
    text = unescape(re.sub(r"\n{3,}", "\n\n", text))
    return text.strip()


def _parse_politician_name(title: str, soup: BeautifulSoup) -> tuple[str, str]:
    author = soup.select_one(".p_seijika_detail_bottom_author_data_ttl a")
    name = ""
    if author:
        name = author.get_text(strip=True)
    else:
        m = re.search(r"-\s*(.+?)（", title)
        if m:
            name = m.group(1).strip()
        else:
            m = re.search(r"-\s*(.+?)\s*｜", title)
            if m:
                name = m.group(1).strip()
            else:
                name = "政治家"

    reading = ""
    m = re.search(r"（([ァ-ヶー・\s]+)）", title)
    if m:
        reading = m.group(1).strip()
    return name, reading


def _seijika_profile_url(post_url: str) -> str | None:
    m = re.search(r"(https?://[^/]+/seijika/\d+)", post_url)
    return m.group(1) if m else None


def _parse_personal_table(soup: BeautifulSoup) -> dict[str, str]:
    data: dict[str, str] = {}
    table = soup.select_one(".p_seijika_personal_table")
    if not table:
        return data
    for tr in table.select("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if len(cells) >= 2:
            data[cells[0]] = cells[1]
    return data


def _enrich_politician_from_profile(
    politician: PoliticianInfo,
    post_url: str,
    session: requests.Session,
) -> PoliticianInfo:
    """プロフィール頁からフリガナ・年齢・性別を補完。"""
    profile_url = _seijika_profile_url(post_url)
    if not profile_url:
        return politician
    try:
        resp = session.get(profile_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except requests.RequestException:
        return politician

    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if not politician.name_reading:
        m = re.search(r"（([ァ-ヶー・\s]+)）", title)
        if m:
            politician.name_reading = m.group(1).strip()

    personal = _parse_personal_table(soup)
    if not politician.age and personal.get("年齢"):
        politician.age = personal["年齢"].strip()
    if not politician.gender:
        raw_gender = personal.get("性別", "").strip()
        if raw_gender in ("男", "男性"):
            politician.gender = "男性"
        elif raw_gender in ("女", "女性"):
            politician.gender = "女性"
        elif raw_gender:
            politician.gender = raw_gender
    return politician


def _parse_district(soup: BeautifulSoup) -> str:
    block = soup.select_one(".p_seijika_detail_bottom_author_data_right")
    if not block:
        return ""
    raw = block.get_text(" ", strip=True)
    m = re.search(
        r"((?:[^\s\d][^\s]*?(?:都|道|府|県|市|区|町|村)[^\s]*?(?:第?\d+)?区)|"
        r"[^\s]*?(?:都|道|府|県|市|区|町|村)(?:議会|選挙)[^\s]*?(?:議員|候補)?)",
        raw,
    )
    if m:
        return re.sub(r"\(\d{4}/\d{2}/\d{2}\).*", "", m.group(1)).strip()
    for li in block.select("li"):
        txt = li.get_text(" ", strip=True)
        if "選挙" in txt or "議会" in txt:
            txt = re.sub(r"\(\d{4}/\d{2}/\d{2}\).*", "", txt).strip()
            txt = re.sub(r"\s*\d+[\s,]*票\s*$", "", txt).strip()
            if txt:
                return txt
    return ""


def _parse_party(soup: BeautifulSoup) -> str:
    block = soup.select_one(".p_seijika_detail_bottom_author_data_right")
    if not block:
        return ""
    for li in block.select("li"):
        txt = li.get_text(strip=True)
        if "党" in txt and "選挙" not in txt:
            return txt
    return ""


def _party_color(party: str) -> str:
    colors = {
        "自由民主党": "#E60012",
        "立憲民主党": "#004098",
        "日本維新の会": "#009944",
        "公明党": "#F3981D",
        "日本共産党": "#DB0202",
        "国民民主党": "#FFCC00",
        "れいわ新選組": "#E4007F",
        "社会民主党": "#FF8C00",
        "参政党": "#FF8F00",
    }
    for key, color in colors.items():
        if key in party:
            return color
    return "#555555"


def _extract_youtube_embeds(content) -> list[tuple[str, bool, bool]]:
    """iframe / oembed → (video_id, is_short, is_live)。本文中の plain link は除外。"""
    found: list[tuple[str, bool, bool]] = []
    seen: set[str] = set()

    def _push(vid: str, url: str = "") -> None:
        if vid in seen:
            return
        seen.add(vid)
        low = url.lower()
        is_short = "shorts" in low
        is_live = any(tok in low for tok in ("/live", "live_stream", "feature=live", "is_live=1"))
        found.append((vid, is_short, is_live))

    for iframe in content.select("iframe[src*='youtube.com'], iframe[src*='youtube-nocookie.com']"):
        src = iframe.get("src", "")
        if "live_stream" in src or "/live" in src:
            m = re.search(r"[?&]v=([A-Za-z0-9_-]+)", src)
            if m:
                _push(m.group(1), src)
                continue
            # channel live without v= — mark as live with empty handled later via URL
            m = re.search(r"embed/([A-Za-z0-9_-]+)", src)
            if m:
                _push(m.group(1), src + "&feature=live")
                continue
        m = re.search(r"embed/([A-Za-z0-9_-]+)", src)
        if m:
            _push(m.group(1), src)

    for node in content.select("[data-oembed-url]"):
        url = node.get("data-oembed-url", "")
        for pat in YOUTUBE_PATTERNS:
            m = pat.search(url)
            if m:
                _push(m.group(1), url)
                break

    return found


def _extract_direct_videos(content, content_html: str) -> list[str]:
    """直接アップロードされた動画 URL（埋め込み以外）。"""
    urls: list[str] = []
    seen: set[str] = set()

    for video in content.select("video"):
        src = video.get("src") or ""
        if not src:
            source = video.select_one("source[src]")
            src = source.get("src") if source else ""
        if src and src not in seen and not any(p in src for p in ("youtube", "facebook", "instagram")):
            seen.add(src)
            urls.append(src)

    for m in re.finditer(r'(https?://[^\s\"\']+\.mp4(?:\?[^\s\"\']*)?)', content_html):
        url = m.group(1)
        if url not in seen and not any(p in url for p in ("youtube", "facebook", "instagram")):
            seen.add(url)
            urls.append(url)

    return urls


def _extract_instagram_urls(content_html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for m in re.finditer(r'data-instgrm-permalink="([^"]+)"', content_html):
        url = m.group(1).split("?")[0].rstrip("/") + "/"
        if url not in seen:
            seen.add(url)
            urls.append(url)

    for m in re.finditer(r'https://www\.instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_-]+/?', content_html):
        url = m.group(0).split("?")[0].rstrip("/") + "/"
        if url not in seen:
            seen.add(url)
            urls.append(url)

    for iframe in BeautifulSoup(content_html, "html.parser").select("iframe[src*='instagram.com']"):
        src = iframe.get("src", "")
        m = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", src)
        if m:
            url = f"https://www.instagram.com/p/{m.group(1)}/"
            if url not in seen:
                seen.add(url)
                urls.append(url)

    return urls


def _extract_facebook_videos(content_html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'data-href="(https://www\.facebook\.com/[^"]+)"', content_html):
        url = m.group(1)
        if "video" not in url and "/reel/" not in url and "/watch" not in url:
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _extract_content_images(content) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for img in content.select("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not src or src in seen:
            continue
        if "politician_profile" in src or "favicon" in src:
            continue
        seen.add(src)
        urls.append(src)
    return urls


def scrape_go2senkyo_post(url: str, session: requests.Session | None = None) -> ScrapedPost:
    session = session or _session()
    resp = session.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    page_title = title_tag.get_text(strip=True) if title_tag else ""
    h1 = soup.select_one(".p_seijika_detail_ttl")
    title = h1.get_text(strip=True) if h1 else page_title.split(" - ")[0]

    content = soup.select_one("section.p_seijika_detail_contents")
    if not content:
        raise ValueError(f"記事本文が見つかりません: {url}")

    text = _clean_text(content)
    name, reading = _parse_politician_name(page_title, soup)
    district = _parse_district(soup)
    party = _parse_party(soup)

    portrait = ""
    portrait_el = soup.select_one(".p_seijika_detail_bottom_author_data_image img")
    if portrait_el:
        portrait = (portrait_el.get("data-src") or portrait_el.get("src") or "").strip()
    if not portrait:
        m = re.search(r'data-history_image="([^"]+)"', html)
        if m:
            portrait = m.group(1).strip()

    media: list[ScrapedMedia] = []
    content_html = str(content)

    for i, img_url in enumerate(_extract_content_images(content)):
        media.append(ScrapedMedia(id=f"img_{i+1}", kind="image", url=img_url))

    for i, video_url in enumerate(_extract_direct_videos(content, content_html)):
        media.append(ScrapedMedia(id=f"video_{i+1}", kind="video", url=video_url))

    for i, (vid, is_short, is_live) in enumerate(_extract_youtube_embeds(content)):
        watch_url = f"https://www.youtube.com/watch?v={vid}"
        if is_live:
            watch_url = f"https://www.youtube.com/embed/live_stream?v={vid}"
        media.append(
            ScrapedMedia(
                id=f"yt_{i+1}",
                kind="embed_thumbnail",
                url=watch_url,
                embed_platform="youtube",
                video_id=vid,
                is_short=is_short,
                is_live=is_live,
            )
        )

    for i, fb_url in enumerate(_extract_facebook_videos(content_html)):
        media.append(
            ScrapedMedia(
                id=f"fb_{i+1}",
                kind="embed_thumbnail",
                url=fb_url,
                embed_platform="facebook",
            )
        )

    for i, ig_url in enumerate(_extract_instagram_urls(content_html)):
        media.append(
            ScrapedMedia(
                id=f"ig_{i+1}",
                kind="embed_thumbnail",
                url=ig_url,
                embed_platform="instagram",
            )
        )

    og = soup.find("meta", property="og:image")
    og_image = og["content"] if og and og.get("content") else ""
    has_content_images = any(m.kind == "image" for m in media)
    has_embeds = any(m.kind == "embed_thumbnail" for m in media)

    if not has_content_images and og_image and not has_embeds:
        if "blogit/post/thumbnail" in og_image or "ckeditor/pictures" in og_image:
            media.append(ScrapedMedia(id="thumb_og", kind="thumbnail", url=og_image))
        elif not media and portrait:
            media.append(ScrapedMedia(id="portrait", kind="thumbnail", url=portrait))

    politician = PoliticianInfo(
        name=name,
        name_reading=reading,
        district=district or "選挙区",
        party=party,
        party_color=_party_color(party),
    )
    politician = _enrich_politician_from_profile(politician, url, session)

    return ScrapedPost(
        source_url=url,
        post_id=_extract_post_id(url),
        title=title,
        text=text,
        politician=politician,
        media=media,
        portrait_url=portrait,
    )
