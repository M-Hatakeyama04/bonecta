# Bonecta（ボネクタ）プロトタイプ

政治家向けSNS運用支援 — ブログ記事から **9:16 縦型ショート動画（15〜20秒）** を自動生成するツールです。

## クイックスタート

```bash
pip install -r requirements.txt
python scripts/setup_assets.py            # img/logo.png, bgm/ 初期化
python scripts/generate_sample_media.py   # テスト用画像・動画
python main.py                            # MP4 を output/ に出力
python scripts/batch_go2senkyo.py         # go2senkyo 18本一括生成
```

## オーバーレイ・音声

- **右下ロゴ:** 全編通して `img/logo.png` を表示（差し替え可）
- **エンドカード:** 末尾約3秒「ボネクタで情報発信中！」+ ロゴ
- **BGM:** `bgm/` 内ファイルをランダム再生（直接取得した動画に音声がある場合は動画音声を優先）

## 埋め込み動画の扱い（転載防止）

YouTube / Facebook / Instagram の**埋め込みは動画本体を使いません**。
**政治家ポートレート**を表示し、プラットフォーム名バッジ（「YouTubeで公開中」等）を重ねます。

## 構成ルール（優先順位）

1. **直接アップロード動画** … 横長は強ボカシ背景。音声ありなら動画音声を優先。
2. **画像 / 埋め込み（ポートレート）** … 最大5枚。0.5秒クロスフェード。
3. **テロップ** … 20文字×最大5枚。本編に同期。
4. **エンドカード** … 末尾3秒。

## 設計方針（複雑なブログパターンへの対応）

go2senkyo.com には多様な記事パターンがありますが、**個別分岐を増やさず** 次の統一パイプラインで処理します。

```
BlogPost → Analyzer（分類・安全チェック）
        → Composer（タイムライン組み立て）
        → Renderer（FFmpeg 多段レンダリング）
        → MP4
```

### パターン分類（BlogPattern）

| カテゴリ | 例 | 処理 |
|---------|-----|------|
| 横画像のみ | 16:9 写真 | ブラー背景 + 中央配置スライドショー |
| 縦画像のみ | 9:16 自撮り | 全画面表示 |
| 横+縦混在 | 複数比率 | 各素材のレイアウトルールを個別適用 |
| 小さい画像 | 640px 級 | ブラー背景 + 中央（拡大しすぎない） |
| 動画（横） | YouTube 通常 | **最優先**・先頭15秒・**ミュート**・ブラー背景 |
| 動画（縦） | ショート / 縦撮影 | 全画面 |
| 動画+画像混在 | 演説+写真 | 動画→画像クロスフェード |
| リンク切れ | 404 embed | スキップして画像/単色背景で継続 |
| 画像なし | テキストのみ | 政党カラー単色 + テロップ |

## ファイル構成

```
bonecta/
  models.py     # データモデル・BlogPattern 列挙
  analyzer.py   # 記事解析・安全チェック
  telop.py      # テロップ生成（LLM 差し替え可能）
  composer.py   # タイムライン計画
  renderer.py   # FFmpeg レンダリング
data/
  sample_post.json
  media/        # generate_sample_media.py で生成
output/         # 生成 MP4・ffmpeg_plan.json
main.py         # CLI エントリポイント
```

## 本番拡張ポイント

- `telop.py` → Gemini / GPT で要約・分割
- `analyzer.py` → go2senkyo HTML スクレイパー + YouTube ダウンロード
- `renderer.py` → 実 BGM アセット、フォント設定、Code Connect 的テンプレ

## go2senkyo パターン一覧

ユーザー提供 URL は `BlogPattern` として分類可能です。スクレイパー実装時は HTML から `MediaAsset` を抽出し、同じ Composer / Renderer に渡してください。
