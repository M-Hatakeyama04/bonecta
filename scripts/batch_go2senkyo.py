#!/usr/bin/env python3
"""go2senkyo.com ブログ記事を一括でショート動画化"""

from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bonecta.analyzer import parse_blog_post
from bonecta.composer import build_video_plan
from bonecta.media_fetcher import fetch_media_for_post
from bonecta.renderer import render_video
from bonecta.scraper import scrape_go2senkyo_post

BATCH_POSTS: list[tuple[str, str, str]] = [
    ("01_images_landscape", "横画像", "https://go2senkyo.com/seijika/198426/posts/1348642"),
    ("02_images_landscape_small", "横画像（小）", "https://go2senkyo.com/seijika/193945/posts/1403337"),
    ("03_images_portrait", "縦画像", "https://go2senkyo.com/seijika/182830/posts/1403342"),
    ("04_images_mixed", "横+縦混在", "https://go2senkyo.com/seijika/157281/posts/1403336"),
    ("05_images_portrait_small", "縦画像（小）", "https://go2senkyo.com/seijika/185576/posts/515935"),
    ("06_no_images_with_thumb", "画像なし（サムネ）", "https://go2senkyo.com/seijika/183086/posts/1396802"),
    ("07_no_images_no_thumb", "画像なし", "https://go2senkyo.com/seijika/198127/posts/1403340"),
    ("08_video_youtube_landscape_1", "YouTube横", "https://go2senkyo.com/seijika/187819/posts/1403319"),
    ("09_video_youtube_landscape_2", "YouTube横2", "https://go2senkyo.com/seijika/168370/posts/662536"),
    ("10_video_youtube_short", "YouTube Short", "https://go2senkyo.com/seijika/166988/posts/1387097"),
    ("11_video_portrait", "縦動画(FB)", "https://go2senkyo.com/seijika/77537/posts/1403327"),
    ("12_video_broken", "リンク切れ", "https://go2senkyo.com/seijika/148720/posts/1403333"),
    ("13_mixed_img_portrait_video", "横画像+縦動画", "https://go2senkyo.com/seijika/196232/posts/1279675"),
    ("14_mixed_youtube_landscape_img", "YouTube+横画像", "https://go2senkyo.com/seijika/180432/posts/911646"),
    ("15_mixed_youtube_short_portrait", "Short+縦画像", "https://go2senkyo.com/seijika/196232/posts/1285333"),
    ("16_mixed_youtube_portrait_img", "YouTube+縦画像", "https://go2senkyo.com/seijika/191793/posts/831867"),
    ("17_special_live", "ライブ埋込", "https://go2senkyo.com/seijika/185863/posts/773050"),
    ("18_special_embed", "特殊埋込", "https://go2senkyo.com/seijika/141939/posts/1364579"),
]

OUTPUT_ROOT = ROOT / "output" / "go2senkyo"


def slugify(text: str) -> str:
    return re.sub(r"[^\w\-]+", "_", text)[:40].strip("_")


def process_one(slug: str, label: str, url: str) -> dict:
    out_dir = OUTPUT_ROOT / slug
    media_dir = out_dir / "media"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}\n[{slug}] {label}\n{url}")

    scraped = scrape_go2senkyo_post(url)
    media_specs, portrait_path = fetch_media_for_post(scraped, media_dir)

    meta = {
        "slug": slug,
        "label": label,
        "url": url,
        "title": scraped.title,
        "politician": scraped.politician.__dict__,
        "media_specs": media_specs,
        "portrait_path": str(portrait_path) if portrait_path else None,
        "text_preview": scraped.text[:200],
    }
    (out_dir / "post.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    post = parse_blog_post(
        text=scraped.text,
        politician=scraped.politician,
        media_specs=media_specs,
        local_media_dir=media_dir,
    )
    post.portrait_path = portrait_path

    plan = build_video_plan(post)
    output_mp4 = out_dir / f"{slug}.mp4"

    print(f"  政治家: {scraped.politician.name}" + (f"（顔写真あり）" if portrait_path else "（顔写真なし）"))
    print(f"  パターン: {post.pattern.value if post.pattern else '-'}")
    print(f"  素材: {len([m for m in post.media if m.is_usable])} 件 / セグメント {len(plan.segments)}")

    render_video(plan, output_mp4, work_dir=out_dir / ".work")

    return {
        "slug": slug,
        "label": label,
        "url": url,
        "output": str(output_mp4.resolve()),
        "pattern": post.pattern.value if post.pattern else None,
        "status": "ok",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="既存 MP4 も再生成")
    args = parser.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    errors: list[dict] = []

    for slug, label, url in BATCH_POSTS:
        out_mp4 = OUTPUT_ROOT / slug / f"{slug}.mp4"
        if out_mp4.exists() and not args.force:
            print(f"[skip] {slug} 既存")
            results.append({"slug": slug, "output": str(out_mp4), "status": "skipped"})
            continue
        try:
            results.append(process_one(slug, label, url))
            print(f"  ✓ 完了: {OUTPUT_ROOT / slug / (slug + '.mp4')}")
        except Exception as exc:
            errors.append({"slug": slug, "url": url, "error": str(exc)})
            print(f"  ✗ 失敗: {exc}")
            traceback.print_exc()

    summary = {"ok": results, "errors": errors}
    summary_path = OUTPUT_ROOT / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"成功: {len(results)} / 失敗: {len(errors)} / 合計: {len(BATCH_POSTS)}")
    print(f"サマリー: {summary_path}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
