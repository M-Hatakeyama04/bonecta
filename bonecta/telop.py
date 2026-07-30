from __future__ import annotations

import re

from bonecta.models import TelopSlide

MAX_SLIDES = 5
MAX_CHARS_PER_SLIDE = 24
TELOP_SLIDE_DURATION = 4.0
LAST_TELOP_CONTINUATION = "……（続く）"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？\n]+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _strip_urls(text: str) -> str:
    return re.sub(r"https?://\S+", "", text).strip()


def _chunk_text(text: str, max_len: int = MAX_CHARS_PER_SLIDE) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_len:
            chunks.append(rest)
            break
        window = rest[: max_len + 1]
        cut = -1
        for sep in ("。", "、", "！", "？", "」", "）", "・", "は", "が", "を", "に", "で", "と"):
            pos = window.rfind(sep)
            if pos > max_len // 3:
                cut = pos + (1 if sep in "。、！？」）" else 0)
                break
        if cut <= 0:
            cut = max_len
        piece = rest[:cut].strip()
        if piece:
            chunks.append(piece)
        rest = rest[cut:].strip()

    return chunks


def _rule_based_telops(blog_text: str) -> list[str]:
    """ブログ本文をそのまま分割してテロップ候補にする（整形なし）。"""
    text = _strip_urls(blog_text)
    sentences = _split_sentences(text)
    candidates: list[str] = []
    used: set[str] = set()

    for sentence in sentences:
        for chunk in _chunk_text(sentence):
            trimmed = chunk[:MAX_CHARS_PER_SLIDE].strip()
            if trimmed and trimmed not in used:
                candidates.append(trimmed)
                used.add(trimmed)
            if len(candidates) >= MAX_SLIDES:
                break
        if len(candidates) >= MAX_SLIDES:
            break

    if not candidates:
        candidates = ["活動報告をお届けします"]

    return candidates[:MAX_SLIDES]


def _with_continuation_mark(text: str) -> str:
    """最終テロップに続きもの感を付ける。"""
    if "（続く）" in text or text.endswith("..."):
        return text
    if text.endswith("……") or text.endswith("…"):
        base = text.rstrip(".…")
        return f"{base}{LAST_TELOP_CONTINUATION}"

    room = MAX_CHARS_PER_SLIDE - len(LAST_TELOP_CONTINUATION)
    base = text[:room].rstrip("。、！？!?.…")
    return f"{base}{LAST_TELOP_CONTINUATION}"


def generate_telop_slides(
    blog_text: str,
    total_duration: float,
    _num_segments: int = 1,
) -> list[TelopSlide]:
    """ブログ本文からテロップを生成（整形なし・1枚4秒）。"""
    slides_text = _rule_based_telops(blog_text)
    max_fit = max(1, int(total_duration // TELOP_SLIDE_DURATION))
    slides_text = slides_text[: min(len(slides_text), MAX_SLIDES, max_fit)]

    if slides_text:
        slides_text[-1] = _with_continuation_mark(slides_text[-1])

    slides: list[TelopSlide] = []
    for i, txt in enumerate(slides_text):
        start = i * TELOP_SLIDE_DURATION
        end = start + TELOP_SLIDE_DURATION
        slides.append(TelopSlide(index=i + 1, text=txt, start_sec=start, end_sec=end))

    return slides
