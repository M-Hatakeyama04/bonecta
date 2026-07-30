from __future__ import annotations

import random
from pathlib import Path

from bonecta.paths import BGM_DIR

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".mp4", ".mkv", ".mov"}


def list_bgm_files(bgm_dir: Path | None = None) -> list[Path]:
    bgm_dir = bgm_dir or BGM_DIR
    if not bgm_dir.is_dir():
        return []
    files = [
        p
        for p in bgm_dir.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS and not p.name.startswith(".")
    ]
    return sorted(files)


def pick_random_bgm(bgm_dir: Path | None = None) -> Path | None:
    files = list_bgm_files(bgm_dir)
    if not files:
        return None
    return random.choice(files)
