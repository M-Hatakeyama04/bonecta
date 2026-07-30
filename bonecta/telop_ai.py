from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

MAX_SLIDES = 5
MAX_CHARS_PER_SLIDE = 24

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:latest")

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# 言い尻が中途半端な行末（助詞・読点で終わる）
_BAD_ENDING = re.compile(r"(を|が|に|で|と|は|も|へ|や|、|，|け|し|せ|れ)$")
# 自然に締まった行末
_GOOD_ENDING = re.compile(
    r"(です|ます|した|でした|ません|いました|あります|おります|ございます|"
    r"ください|しょう|ませんか|でしょう|！|!|？|\?|。)$"
)

_REFINE_PROMPT = """あなたは政治家のショート動画（縦型9:16・15〜20秒）用テロップ編集者です。
下書きテロップを、画面に表示する完成形に整えてください。

## 絶対ルール
1. 各行は全角{max_chars}文字以内（句読点含む）。超えたら言い換えて短く
2. 各行は意味が完結した一文・一節にする
3. 言い尻（最重要）:
   - 禁止: 「〜を」「〜が」「〜に」「〜で」「〜と」「〜、」で終わる行
   - 禁止: 接続詞だけで次に続く途中切れ（「〜しましたが、」のような未完）
   - 推奨: 「〜です」「〜ます」「〜した！」「〜しました」などで締める
4. {min_slides}〜{max_slides}行。元の時系列と主旨は維持
5. 煽りすぎず、活動報告として自然な口調
6. 改行は入れない（1要素＝1テロップ）

## 出力形式
JSONのみ。説明文は書かない。
{{"telops": ["1行目", "2行目", ...]}}

## ブログ本文（参照用）
{blog_excerpt}

## 下書き（これを整える）
{drafts_json}
"""


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            raw = m.group(0)
            raw = raw.replace("「", '"').replace("」", '"')
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    return None


def _is_valid_line(line: str) -> bool:
    if not line or len(line) > MAX_CHARS_PER_SLIDE:
        return False
    if _BAD_ENDING.search(line):
        return False
    if not _GOOD_ENDING.search(line):
        return False
    return True


def _normalize_telops(raw: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        line = re.sub(r"\s+", "", item.strip())
        line = line.replace("「", "").replace("」", "")
        if not line or not _is_valid_line(line):
            continue
        if line not in seen:
            out.append(line)
            seen.add(line)
        if len(out) >= MAX_SLIDES:
            break
    return out


def _ollama_available() -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _call_ollama(prompt: str, *, temperature: float = 0.35) -> str | None:
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature, "num_predict": 512},
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("response")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def refine_telops_with_ollama(drafts: list[str], blog_text: str) -> list[str] | None:
    """
    ローカル Ollama で下書きテロップを整える。
    環境変数: OLLAMA_HOST (default http://localhost:11434), OLLAMA_MODEL (default gemma3:latest)
    """
    if not drafts or not _ollama_available():
        return None

    prompt = _REFINE_PROMPT.format(
        max_chars=MAX_CHARS_PER_SLIDE,
        min_slides=3,
        max_slides=MAX_SLIDES,
        blog_excerpt=blog_text[:2000],
        drafts_json=json.dumps(drafts, ensure_ascii=False),
    )

    response = _call_ollama(prompt)
    if not response:
        return None

    data = _extract_json(response)
    if not data or "telops" not in data:
        return None

    telops = _normalize_telops(data["telops"])
    if len(telops) >= 2:
        return telops

    # バリデーション不合格時は温度を下げて1回だけ再試行
    retry_prompt = prompt + "\n\n前回の出力に言い尻が不自然な行がありました。各行は必ず「です」「ます」「した」「！」などで締めてください。"
    response = _call_ollama(retry_prompt, temperature=0.2)
    if not response:
        return None
    data = _extract_json(response)
    if not data or "telops" not in data:
        return None
    telops = _normalize_telops(data["telops"])
    if len(telops) < 2:
        return None
    return telops


def generate_telops_with_gemini(blog_text: str) -> list[str] | None:
    """Gemini API（クラウド）フォールバック。GEMINI_API_KEY / GOOGLE_API_KEY"""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    system = _REFINE_PROMPT.format(
        max_chars=MAX_CHARS_PER_SLIDE,
        min_slides=3,
        max_slides=MAX_SLIDES,
        blog_excerpt=blog_text[:2000],
        drafts_json="（下書きなし・ブログから新規作成）",
    )

    body = {
        "contents": [{"role": "user", "parts": [{"text": system}]}],
        "generationConfig": {"temperature": 0.5, "responseMimeType": "application/json"},
    }

    req = urllib.request.Request(
        f"{GEMINI_URL}?key={api_key}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None

    data = _extract_json(text)
    if not data or "telops" not in data:
        return None

    telops = _normalize_telops(data["telops"])
    return telops if len(telops) >= 2 else None
