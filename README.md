# Bonecta（ボネクタ）プロトタイプ

政治家向けSNS運用支援 — ブログ記事（go2senkyo.com 活動記録）から **9:16 縦型ショート動画** を自動生成するツールです。

## ドキュメント

| 資料 | 用途 |
|------|------|
| [`docs/html/index.html`](docs/html/index.html) | **ブラウザ向け HTML パッケージ（印刷・PDF 可）** |
| [`docs/開発依頼書.md`](docs/開発依頼書.md) | 開発会社への依頼・要件・検収 |
| [`docs/VIDEO_SPEC.md`](docs/VIDEO_SPEC.md) | 動画の詳細仕様（表示ルール・UI・フォント） |
| [`docs/共有パッケージ.md`](docs/共有パッケージ.md) | 発注時に何を渡すかの案内 |

## クイックスタート

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# システム依存: ffmpeg / ffprobe が必要
python scripts/setup_assets.py            # ロゴ等の初期化
python scripts/batch_go2senkyo.py         # go2senkyo 一括生成
python scripts/batch_go2senkyo.py --force # 再生成
```

生成結果は `output/go2senkyo/{slug}/{slug}.mp4`（Git 管理外）。

## 素材表示ルール（要約）

| 記事の内容 | 表示 | テロップ |
|------------|------|----------|
| 画像のみ | 画像 | あり |
| 画像なし | 政治家画像 | あり |
| 直接動画（画像の有無問わず） | 動画 | **なし** |
| YouTube（通常） | サムネイル | あり |
| YouTube Live / Facebook / Instagram | 政治家画像 | あり |

詳細は `docs/VIDEO_SPEC.md` を参照。

## フォント

- 同梱: `fonts/NotoSansJP-VF.ttf` のみ使用（端末差なし）
- テロップ weight **500** / 名前・CTA **700** / メタ **400**

## 主な構成

```
bonecta/           # 本体ライブラリ
scripts/           # バッチ・セットアップ
docs/              # 仕様・依頼資料
fonts/             # Noto Sans JP VF
bgm/               # BGM
img/               # ロゴ
output/            # 生成物（gitignore）
```
