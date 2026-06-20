import os
import sys
import json
import re
import argparse
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import html
import subprocess
from datetime import datetime, timezone, timedelta

# 標準出力をUTF-8に設定
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JST = timezone(timedelta(hours=9))

def load_env():
    """ローカルの .env ファイルをロードして環境変数に設定する"""
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()


FEEDS = [
    {
        "url": "https://zenn.dev/feed",
        "category": "IT",
        "source": "Zenn"
    },
    {
        "url": "https://b.hatena.ne.jp/hotentry/it.rss",
        "category": "AI",
        "source": "Hatena IT"
    }
]

def clean_filename(filename):
    """Windowsのファイル名として不適切な文字を置換する"""
    filename = filename.replace("\\", "＼").replace("/", "／")
    filename = filename.replace(":", "：").replace("*", "＊")
    filename = filename.replace("?", "？").replace('"', "”")
    filename = filename.replace("<", "＜").replace(">", "＞")
    filename = filename.replace("|", "｜")
    return filename.strip()

def fetch_news_from_rss(feed_info):
    url = feed_info["url"]
    source = feed_info["source"]
    print(f"🐾 RSSフィードを取得中: {url} ({source})")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        
        items = root.findall('.//item')
        if not items:
            items = root.findall('.//{http://purl.org/rss/1.0/}item')
        if not items:
            items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
            
        news_items = []
        for item in items[:15]:  # AI関連をフィルタするために少し多めに走査
            title_el = item.find('title')
            if title_el is None or not title_el.text:
                continue
            title = html.unescape(title_el.text.strip())
            
            # AI関連かチェック
            t_upper = title.upper()
            is_ai = any(kw in t_upper for kw in ["AI", "LLM", "GPT", "人工知能", "機械学習", "DEEP LEARNING", "TRANSFORMER", "CLAUDE", "GEMINI", "OLLAMA", "STABLE DIFFUSION", "MEMBER-DEEPDIVE", "AGENTS"])
            if not is_ai:
                continue

            link_el = item.find('link')
            link = ""
            if link_el is not None:
                link = link_el.text if link_el.text else link_el.get('href', '')
            if not link:
                continue
            link = link.strip()
            
            pub_date_el = item.find('pubDate')
            if pub_date_el is None:
                pub_date_el = item.find('{http://purl.org/dc/elements/1.1/}date')
            if pub_date_el is None:
                pub_date_el = item.find('{http://www.w3.org/2005/Atom}published')
                
            pub_date = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else datetime.now(timezone.utc).isoformat()
            
            news_items.append({
                "title": title,
                "url": link,
                "published_at": pub_date,
                "summary": title
            })
        return news_items
    except Exception as e:
        print(f"⚠️ RSS取得エラー ({url}): {e}")
        return []

def get_recent_titles(news_json_path):
    recent_titles = []
    if os.path.exists(news_json_path):
        try:
            with open(news_json_path, "r", encoding="utf-8") as f:
                news_data = json.load(f)
                for item in news_data:
                    if "title" in item:
                        recent_titles.append(item["title"])
        except Exception as e:
            print(f"⚠️ news.json の読み込みエラー: {e}")
    return recent_titles

def call_gemini_api(api_key, system_prompt, user_content):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    data = {
        "systemInstruction": {
            "parts": [
                {"text": system_prompt}
            ]
        },
        "contents": [{
            "role": "user",
            "parts": [{"text": user_content}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            text_response = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            return text_response
    except Exception as e:
        print(f"⚠️ Gemini API 呼び出しエラー: {e}")
        return None

def main():
    load_env()
    parser = argparse.ArgumentParser(description="夜のニュース日記自動生成スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="Gitへのプッシュを行わずに実行します")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ エラー: 環境変数 GEMINI_API_KEY が設定されていません。")
        sys.exit(1)

    # 処理開始前に git pull でリモートに追いつく
    if not args.dry_run:
        print("🐾 リモートから最新情報を取得中 (git pull)...")
        try:
            subprocess.run(["git", "pull"], check=True, cwd=BASE_DIR)
            print("🐾 リモートの最新情報を取得しました。")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ 警告: git pull に失敗しました。競合があるか、またはオフライン環境の可能性があります: {e}")

    print("🐾 夜のニュース日記の自動生成を開始します。")

    # 1. ニュース候補の収集
    candidates = []
    for feed in FEEDS:
        candidates.extend(fetch_news_from_rss(feed))
    
    seen_urls = set()
    unique_candidates = []
    for c in candidates:
        if c["url"] not in seen_urls:
            seen_urls.add(c["url"])
            unique_candidates.append(c)
    
    print(f"🐾 候補ニュースを {len(unique_candidates)} 件検出しました。")
    if not unique_candidates:
        print("❌ エラー: AI 関連の候補ニュースが見つかりませんでした。処理を終了します。")
        sys.exit(0)

    # 2. 直近記事タイトルの取得
    news_json_path = os.path.join(BASE_DIR, "news.json")
    recent_titles = get_recent_titles(news_json_path)

    # 3. 日付の設定
    execution_date = datetime.now(JST).strftime("%Y-%m-%d")

    # 4. プロンプト（指示書）の読み込み
    prompt_path = os.path.join(BASE_DIR, "news-pronpt.md")
    if not os.path.exists(prompt_path):
        print(f"❌ エラー: プロンプトファイルが見つかりません: {prompt_path}")
        sys.exit(1)
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # 5. 入力コンテキストの作成
    context = {
        "execution_date": execution_date,
        "recent_titles": recent_titles[:15],
        "news_candidates": unique_candidates[:8]
    }
    user_content = json.dumps(context, ensure_ascii=False, indent=2)

    # 6. Gemini API の呼び出し
    print("🐾 Gemini API を呼び出し中...")
    response_text = call_gemini_api(api_key, system_prompt, user_content)
    if not response_text:
        print("❌ エラー: Gemini API からの応答の取得に失敗しました。")
        sys.exit(1)

    # 7. 応答のパースと検証
    try:
        article_data = json.loads(response_text)
    except json.JSONDecodeError as e:
        print("❌ エラー: Gemini の応答が有効な JSON ではありません。")
        print(response_text)
        sys.exit(1)

    # エラーレスポンスのチェック
    if "error" in article_data:
        print(f"⚠️ エージェントがエラーを返しました: {article_data.get('message', '理由不明')}")
        sys.exit(0)

    # 必須フィールドの存在チェック
    required_fields = ["title", "published_at", "category", "score", "description", "comment", "source_type", "content"]
    for field in required_fields:
        if field not in article_data:
            print(f"❌ エラー: 生成された JSON に必須フィールド '{field}' がありません。")
            sys.exit(1)

    print(f"🐾 記事の生成に成功しました: {article_data['title']}")

    # 8. ファイルへの書き出し
    safe_title = clean_filename(article_data["title"])
    filename = f"{safe_title}.json"
    articles_dir = os.path.join(BASE_DIR, "articles")
    if not os.path.exists(articles_dir):
        os.makedirs(articles_dir)
    
    article_path = os.path.join(articles_dir, filename)
    with open(article_path, "w", encoding="utf-8") as f:
        json.dump(article_data, f, ensure_ascii=False, indent=2)
    print(f"🐾 記事ファイルを保存しました: {article_path}")

    # 9. サイトのビルド
    print("🐾 サイトのビルドを実行中 (build_articles.py)...")
    try:
        subprocess.run([sys.executable, "build_articles.py"], check=True, cwd=BASE_DIR)
        print("🐾 ビルドが正常に完了しました。")
    except subprocess.CalledProcessError as e:
        print(f"❌ エラー: build_articles.py の実行に失敗しました: {e}")
        sys.exit(1)

    # 10. X投稿テキストの生成と保存
    print("🐾 X投稿テキストを生成中 (x_post_formatter.py)...")
    xpost_thread_path = os.path.join(articles_dir, f"{safe_title}_xpost_thread.txt")
    xpost_long_path = os.path.join(articles_dir, f"{safe_title}_xpost_long.txt")

    try:
        # スレッド形式
        res_thread = subprocess.run(
            [sys.executable, "x_post_formatter.py", "--article", article_path, "--mode", "thread"],
            capture_output=True, text=True, encoding="utf-8", cwd=BASE_DIR, check=True
        )
        with open(xpost_thread_path, "w", encoding="utf-8") as f:
            f.write(res_thread.stdout)
        print(f"🐾 X投稿（スレッド形式）を保存しました: {xpost_thread_path}")

        # 長文形式
        res_long = subprocess.run(
            [sys.executable, "x_post_formatter.py", "--article", article_path, "--mode", "long"],
            capture_output=True, text=True, encoding="utf-8", cwd=BASE_DIR, check=True
        )
        with open(xpost_long_path, "w", encoding="utf-8") as f:
            f.write(res_long.stdout)
        print(f"🐾 X投稿（長文形式）を保存しました: {xpost_long_path}")

    except subprocess.CalledProcessError as e:
        print(f"⚠️ 警告: x_post_formatter.py の実行中にエラーが発生しました。テキストは保存されません: {e}")

    # 11. Gitコミット＆プッシュ
    if args.dry_run:
        print("🐾 [Dry-run] Git へのコミット・プッシュをスキップします。")
    else:
        print("🐾 Git へのコミット・プッシュを実行中...")
        try:
            # 変更のステージング
            subprocess.run(["git", "add", "articles/*", "news.json", "rss.xml", "index.html"], check=True, cwd=BASE_DIR)
            # コミット
            commit_msg = f"feat: 夜のニュース日記自動配信（{execution_date}）🐾"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=BASE_DIR)
            # プッシュ
            subprocess.run(["git", "push"], check=True, cwd=BASE_DIR)
            print("🐾 Git へのプッシュが完了しました！ブログがデプロイされますわ。")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ 警告: Git へのコミット・プッシュ中にエラーが発生しました。認証設定等を確認してください: {e}")

    print("🐾 すべての処理が正常に完了しました！")

if __name__ == "__main__":
    main()
