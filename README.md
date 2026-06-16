# 🐾 たぬきちゃんのイチオシニュース (Tanuki News)

ご主人様にお届けする、今日の厳選IT・AI・ガジェットニュースまとめサイトですわ！🐾

GitHub Pages を利用して静的公開され、GitHub Actions によって毎日自動でニュースが収集＆たぬきちゃん風のコメントが生成・更新されます。

---

## 🌟 サイトの機能

- **カテゴリフィルタ**: すべて / AI（人工知能） / IT（IT技術） / ガジェット の切り替え
- **リアルタイム検索**: タイトルやコメント内のキーワードで素早く検索
- **おすすめ度**: 各ニュースに対するたぬきちゃんのイチオシ度合いを星（1〜5）で表示
- **たぬきちゃんコメント**: AI（Gemini API）またはフォールバックエンジンによって生成された、愛嬌のあるメイド風ニュース紹介コメント

---

## 📂 構成ファイル

- `index.html`: サイトのメイン構造（Outfit & Zen Maru Gothic フォント使用）
- `style.css`: たぬきブラウン＆オレンジを基調とした上品なレスポンシブデザイン
- `app.js`: クライアントサイドでの動的レンダリングと検索・フィルタリング制御
- `news.json`: ニュースとコメントデータを格納するJSON（データベース代わり）
- `update_news.py`: RSSフィードの取得とGeminiによるコメント自動生成を担うPythonスクリプト
- `assets/tanuki_avatar.png`: たぬきちゃんの可愛らしいアバター画像
- `.github/workflows/update_news.yml`: 毎日AM 7:00（日本時間）にニュースを自動収集して更新するGitHub Actions設定

---

## 🛠 ローカルでの動かし方

### 1. サイトのプレビュー
ローカルでWebサーバーを立ち上げてプレビューします。

```bash
# Python 3 を使って簡易サーバーを起動
python -m http.server 8000
```
起動後、ブラウザで `http://localhost:8000` にアクセスしてください。

### 2. ニュース更新スクリプトの実行
手動でニュースデータを更新したい場合は、以下を実行します。

```bash
# Gemini API を使ってリッチなコメントを生成させる場合（オプション）
set GEMINI_API_KEY=あなたのAPIキー   # Windows CMD
# $env:GEMINI_API_KEY="あなたのAPIキー" # PowerShell
# export GEMINI_API_KEY="あなたのAPIキー" # Bash

python update_news.py
```

---

## 🚀 GitHub Actions 自動更新の設定

自動更新プロセスで本物の Gemini API を動作させるには、GitHubリポジトリ設定にAPIキーを登録してください：

1. GitHubリポジトリの `Settings` > `Secrets and variables` > `Actions` にアクセス
2. `New repository secret` ボタンをクリック
3. Nameに `GEMINI_API_KEY`、Valueにご自身の Gemini APIキーを入力して保存

※ APIキーが設定されていない場合でも、自動で可愛らしいデフォルトコメントテンプレートにフォールバックして動作するため、エラーで止まることはありません。
