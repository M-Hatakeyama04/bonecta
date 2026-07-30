"""
go2senkyo.com ブログ記事パターン参照表

スクレイパー実装時は HTML から MediaAsset を抽出し、
detect_blog_pattern() で分類 → 同一 Composer / Renderer に渡す。

すべてのパターンは以下のレイアウト関数に正規化される:

  portrait_full()      … 9:16 全画面
  landscape_blurbox()  … 強ボカシ背景 + 中央配置
  video_muted()        … 動画は常にミュート、横長は blurbox
  fallback_color()     … 素材なし時は政党カラー
"""

GO2SENKYO_PATTERN_URLS: dict[str, list[str]] = {
    "images_landscape": [
        "https://go2senkyo.com/seijika/198426/posts/1348642",
    ],
    "images_landscape_small": [
        "https://go2senkyo.com/seijika/193945/posts/1403337",
    ],
    "images_portrait": [
        "https://go2senkyo.com/seijika/182830/posts/1403342",
    ],
    "images_mixed": [
        "https://go2senkyo.com/seijika/157281/posts/1403336",
    ],
    "images_portrait_small": [
        "https://go2senkyo.com/seijika/185576/posts/515935",
    ],
    "no_images_with_thumb": [
        "https://go2senkyo.com/seijika/183086/posts/1396802",
    ],
    "no_images_no_thumb": [
        "https://go2senkyo.com/seijika/198127/posts/1403340",
    ],
    "video_youtube_landscape": [
        "https://go2senkyo.com/seijika/187819/posts/1403319",
        "https://go2senkyo.com/seijika/168370/posts/662536",
    ],
    "video_youtube_short": [
        "https://go2senkyo.com/seijika/166988/posts/1387097",
    ],
    "video_portrait": [
        "https://go2senkyo.com/seijika/77537/posts/1403327",
    ],
    "video_broken": [
        "https://go2senkyo.com/seijika/148720/posts/1403333",
    ],
    "mixed_landscape_video_portrait": [
        "https://go2senkyo.com/seijika/196232/posts/1279675",
    ],
    "mixed_youtube_and_images": [
        "https://go2senkyo.com/seijika/180432/posts/911646",
        "https://go2senkyo.com/seijika/196232/posts/1285333",
        "https://go2senkyo.com/seijika/191793/posts/831867",
    ],
    "special_embed": [
        "https://go2senkyo.com/seijika/185863/posts/773050",
        "https://go2senkyo.com/seijika/141939/posts/1364579",
    ],
}
