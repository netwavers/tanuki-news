# 🐾 たぬきちゃんのイチオシニュース (Tanuki News)

ご主人様にお届けする、今日の厳選IT・AI・ガジェットニュースまとめサイトですわ！🐾

GitHub Pages で静的に公開され、**RSS自動収集**と**ご主人様の手動深掘り記事**の2系統を統合して運用しています。

---

## 🌟 サイトの特徴

- **ハイブリッドニュース**: 外部RSS（Zennなど）と、ご主人様が深く書いたオリジナル記事を混在表示
- **source_type による区別**: `rss`（自動収集）と `local`（手動記事）を明確に分離
- **フロントマター対応**: 記事のメタデータ（タイトル・日付・カテゴリ・スコア）をYAMLで厳密管理
- **たぬきちゃんコメント**: Geminiで生成される愛嬌たっぷりのメイド風コメント
- **カテゴリ・検索・おすすめ度**: クライアント側で高速フィルタリング

---

## 📂 主要ファイル構成

| ファイル | 役割 |
|----------|------|
| `news.json` | 全ニュースのマスター（source_type付き） |
| `articles/*.md` | 手動深掘り記事のソース（frontmatter必須） |
| `articles/*.html` | 自動生成される詳細ページ |
| `update_news.py` | **パイプライン段階1**: 外部RSS取得 + `source_type: "rss"` |
| `build_articles.py` | **パイプライン段階2**: ローカル記事ビルド + `source_type: "local"` のマージ |
| `.github/workflows/update_news.yml` | 毎日 + 記事push時に自動実行 |
| `index.html` / `app.js` / `style.css` | フロントエンド |

---

## 🛠 ユーザーが記事を追加する手順（最も重要な操作）

ご主人様が深掘り記事を書きたい場合は、以下の手順で追加してください。

### 1. 記事ファイルを作成する

`articles/` ディレクトリに新しい `.md` ファイルを作成します。

**ファイル名例**:
```
📢 本日の注目ニュース：〇〇〇.md
```

### 2. Frontmatter を必ず先頭に書く

```yaml
---
title: "記事の正式タイトル"
published_at: "2026-06-18T10:00:00Z"   # ISO8601形式推奨
category: "AI"                         # AI / IT / ガジェット
score: 5                               # 1〜5（おすすめ度）
description: "1〜2文程度の短い概要（検索やOGPに使用）"
---
```

- `published_at` は公開日時（UTC推奨）
- `category` は大文字で統一
- 必ず `---` で囲む

### 3. 本文を書く

たぬきちゃん風の口調で自由に書いてください。
- `## **🐾 たぬきちゃんイチオシニュース**` などの見出し推奨
- 後半に `### **🛠️ クリティカル・アーキテクトとしての観察**` などを入れると良い

### 4. ローカルで確認する（推奨）

```bash
# 1. 記事をHTMLに変換 + news.jsonを更新
python build_articles.py

# 2. ローカルサーバーでプレビュー
python -m http.server 8000
```

ブラウザで `http://localhost:8000` を開いて確認。

### 5. Gitでプッシュする

```bash
git add "articles/あなたの記事名.md"
git commit -m "feat: 〇〇〇記事を追加"
git push
```

**これだけで完了です！**

- GitHub Actions が自動で以下を実行します：
  1. `build_articles.py` が `.html` を生成
  2. `news.json` に `source_type: "local"` で登録
  3. コミット＆プッシュ

---

## 🔄 自動化の流れ（パイプライン）

GitHub Actions は**2段階**で動作します（毎日 + 記事push時）：

1. **update_news.py**（外部RSS）
   - Zennなど外部フィードを取得
   - `source_type: "rss"` を付与
   - コメントをGeminiで生成

2. **build_articles.py**（ローカル記事）
   - `articles/*.md` を処理
   - frontmatterを優先してHTML生成
   - `source_type: "local"` を付与
   - RSS記事を尊重しつつマージして `news.json` を再構築

---

## 🖥 ローカル開発

### 記事ビルドのみ手動実行したい場合

```bash
python build_articles.py
```

### RSS収集も手動でやりたい場合

```bash
# Windows
set GEMINI_API_KEY=あなたのキー
python update_news.py

# macOS / Linux
export GEMINI_API_KEY=あなたのキー
python update_news.py
```

### プレビュー

```bash
python -m http.server 8000
```

---

## 🔐 GitHub Actions の設定

自動でGeminiコメントを使うにはリポジトリにシークレットを登録してください。

1. リポジトリの **Settings > Secrets and variables > Actions**
2. `GEMINI_API_KEY` を追加

APIキーがなくても動作します（フォールバックコメントが使われます）。

---

## 📝 Frontmatter 仕様（参考）

| キー            | 必須 | 例                              | 説明                     |
|-----------------|------|----------------------------------|--------------------------|
| title           | ○    | "記事タイトル"                   | 表示タイトル             |
| published_at    | ○    | "2026-06-18T10:00:00Z"           | 公開日時（ISO8601）      |
| category        | ○    | "AI"                             | AI / IT / ガジェット     |
| score           | ○    | 5                                | 1〜5                     |
| description     | ○    | "短い説明文"                     | 検索・OGP用              |

---

## 🧹 注意点・Tips

- 絵文字入りのファイル名も使用可能です（例: 📢 本日の...）
- 自動生成された `.html` は基本的に手動編集しないでください（次回ビルドで上書きされます）
- `news.json` を直接編集するのは非推奨です。スクリプト経由で更新してください。
- RSSとローカル記事は `source_type` で区別されているので、将来的にフィルタリングも可能です。

---

ご主人様の素晴らしい考察や発見を、いつでもこの世界樹に刻んでくださいませ。🐾

何か質問や改善のご要望がございましたら、お気軽におっしゃってくださいね！