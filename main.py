#!/usr/bin/env python3
"""Bonecta CLI - ブログ記事から縦型ショート動画を生成"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bonecta.analyzer import parse_blog_post
from bonecta.composer import build_video_plan
from bonecta.models import PoliticianInfo
from bonecta.renderer import render_video


def load_post(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Bonecta ショート動画ジェネレーター")
    parser.add_argument(
        "--input",
        default=str(ROOT / "data" / "sample_post.json"),
        help="ブログ記事 JSON",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "output" / "yamada_taro_short.mp4"),
        help="出力 MP4 パス",
    )
    parser.add_argument(
        "--media-dir",
        default=str(ROOT / "data" / "media"),
        help="ローカル素材ディレクトリ",
    )
    parser.add_argument("--dry-run", action="store_true", help="FFmpeg 計画のみ出力")
    args = parser.parse_args()

    raw = load_post(Path(args.input))
    politician = PoliticianInfo(**raw["politician"])
    post = parse_blog_post(
        text=raw["text"],
        politician=politician,
        media_specs=raw["media"],
        local_media_dir=Path(args.media_dir),
    )

    plan = build_video_plan(post)
    output = Path(args.output)

    print(f"検出パターン: {post.pattern.value if post.pattern else 'unknown'}")
    print(f"尺: {plan.total_duration:.1f}秒 / セグメント数: {len(plan.segments)}")
    print("テロップ:")
    for t in plan.telops:
        print(f"  [{t.start_sec:.1f}-{t.end_sec:.1f}s] {t.text}")

    render_video(plan, output, dry_run=args.dry_run)

    if args.dry_run:
        print(f"Dry run: {output.parent / 'ffmpeg_plan.json'}")
    else:
        print(f"生成完了: {output.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
