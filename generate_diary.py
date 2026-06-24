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
from email.utils import parsedate_to_datetime

# 標準出力をUTF-8に設定
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JST = timezone(timedelta(hours=9))

from llm_client import (
    DEFAULT_MODEL,
    DEFAULT_FALLBACK_MODEL,
    build_chat_options,
    chat as llm_chat,
    get_llm_client,
    is_ollama_model,
)

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

BACKUP_FEEDS = [
    {
        "url": "https://zenn.dev/topics/ai/feed",
        "category": "AI",
        "source": "Zenn AI"
    },
    {
        "url": f"https://qiita.com/tags/{urllib.parse.quote('人工知能')}/feed",
        "category": "AI",
        "source": "Qiita AI"
    }
]

AI_KEYWORDS = [
    "AI", "LLM", "GPT", "人工知能", "機械学習", "DEEP LEARNING", "TRANSFORMER",
    "CLAUDE", "GEMINI", "OLLAMA", "STABLE DIFFUSION", "MEMBER-DEEPDIVE", "AGENTS",
    "COPILOT", "CHATGPT", "OPENAI", "MCP", "RAG", "DIFFUSION", "推論", "生成AI",
]

TOPIC_STOPWORDS = {
    "ですわ", "ニュース", "日記", "朝の", "夜の", "昼の", "本日の", "巻", "注目",
    "たぬきちゃん", "ご主人様", "の巻", "について", "という", "こと", "ため",
}

TOPIC_SIGNATURES = [
    "claude code", "claude design", "github copilot", "chatgpt", "openai",
    "gemini", "cursor", "xai", "ollama", "localloom", "検証プロセス",
    "コンテキスト", "tmux", "意地悪なqa", "aiコーディング", "生成ai", "人工知能",
    "mcp", "rag", "llm", "agents", "copilot", "stable diffusion", "オールグリーン",
]

def clean_filename(filename):
    """Windowsのファイル名として不適切な文字を置換する"""
    filename = filename.replace("\\", "＼").replace("/", "／")
    filename = filename.replace(":", "：").replace("*", "＊")
    filename = filename.replace("?", "？").replace('"', "”")
    filename = filename.replace("<", "＜").replace(">", "＞")
    filename = filename.replace("|", "｜")
    return filename.strip()

def normalize_topic_title(title):
    normalized = re.sub(r"^📢[^:]*:", "", title)
    normalized = re.sub(r"ですわ.*$", "", normalized)
    normalized = re.sub(r"🐾.*$", "", normalized)
    return normalized.strip().lower()

def extract_topic_signatures(title):
    normalized = normalize_topic_title(title)
    return {term for term in TOPIC_SIGNATURES if term in normalized}

def extract_topic_keywords(title):
    normalized = normalize_topic_title(title)
    keywords = set(extract_topic_signatures(title))
    parts = re.split(r"[、。：「」『』（）\s\-・!?！？🐾/\\|]+", normalized)
    for part in parts:
        part = part.strip("のはがをにでともへやから")
        if len(part) >= 3 and part not in TOPIC_STOPWORDS:
            keywords.add(part)
    keywords.update(re.findall(r"[a-z]{2,}", normalized))
    return keywords

def is_duplicate_topic(candidate_title, recent_titles, threshold=2):
    candidate_keywords = extract_topic_keywords(candidate_title)
    candidate_signatures = extract_topic_signatures(candidate_title)
    if not candidate_keywords and not candidate_signatures:
        return False
    for recent in recent_titles:
        if candidate_signatures & extract_topic_signatures(recent):
            return True
        overlap = candidate_keywords & extract_topic_keywords(recent)
        strong_overlap = {word for word in overlap if len(word) >= 4}
        if len(overlap) >= threshold or strong_overlap:
            return True
    return False

def parse_published_at(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

def is_within_hours(published_at, hours=48, reference=None):
    parsed = parse_published_at(published_at)
    if parsed is None:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    reference = reference or datetime.now(timezone.utc)
    return parsed >= reference - timedelta(hours=hours)

def extract_json_from_response(text):
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)(?:\n?```|$)", cleaned, re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    cleaned = re.sub(r"^-{3,}\s*", "", cleaned)
    object_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if object_match:
        return object_match.group(0)
    return cleaned

def repair_json_text(text):
    """LLM が生成しがちな JSON 構文エラーを修復する"""
    repaired = text
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = re.sub(
        r'("(?:[^"\\]|\\.)*")\s*,\s*\n\s*([^"\n{}\[\]]+)"\s*,',
        lambda match: match.group(1)[:-1] + " " + match.group(2).strip() + '",',
        repaired,
    )
    repaired = re.sub(
        r'("(?:[^"\\]|\\.)*")\s*,\s*\n\s*([^"\n{}\[\]]+)"\s*(\n\s*[}\]])',
        lambda match: match.group(1)[:-1] + " " + match.group(2).strip() + '"' + match.group(3),
        repaired,
    )
    return repaired

def parse_article_json(response_text):
    cleaned = extract_json_from_response(response_text)
    attempts = [cleaned, repair_json_text(cleaned)]
    last_error = None
    for candidate in attempts:
        try:
            return json.loads(candidate), candidate
        except json.JSONDecodeError as error:
            last_error = error
    raise json.JSONDecodeError(str(last_error), cleaned, 0) from last_error

def filter_candidates(candidates, recent_titles, max_age_hours=48):
    reference = datetime.now(timezone.utc)
    filtered = []
    for candidate in candidates:
        if not is_within_hours(candidate.get("published_at"), max_age_hours, reference):
            continue
        if is_duplicate_topic(candidate["title"], recent_titles):
            continue
        filtered.append(candidate)
    return filtered

def fetch_news_from_rss(feed_info, require_ai=True, max_items=30):
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
        for item in items[:max_items]:
            title_el = item.find('title')
            if title_el is None or not title_el.text:
                continue
            title = html.unescape(title_el.text.strip())
            
            t_upper = title.upper()
            is_ai = any(kw in t_upper for kw in AI_KEYWORDS)
            if require_ai and not is_ai:
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

def collect_candidates(feeds, recent_titles):
    candidates = []
    for feed in feeds:
        candidates.extend(fetch_news_from_rss(feed))

    seen_urls = set()
    unique_candidates = []
    for candidate in candidates:
        if candidate["url"] not in seen_urls:
            seen_urls.add(candidate["url"])
            unique_candidates.append(candidate)

    filtered = filter_candidates(unique_candidates, recent_titles)
    if filtered:
        return filtered

    print("🐾 通常フィードの候補が重複または期限切れのため、予備フィードを取得します...")
    for feed in BACKUP_FEEDS:
        candidates.extend(fetch_news_from_rss(feed, require_ai=False))

    unique_candidates = []
    for candidate in candidates:
        if candidate["url"] not in seen_urls:
            seen_urls.add(candidate["url"])
            unique_candidates.append(candidate)

    return filter_candidates(unique_candidates, recent_titles)

def call_llm_api(model_name, system_prompt, user_content, storage_path=None):
    """llm_manager.get_client 経由で記事生成用チャットを実行する"""
    try:
        client = get_llm_client(model_name, storage_path)
        provider = client.config.provider.value
        options = build_chat_options(provider, json_mode=True, temperature=0.2)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        print(f"🐾 LLM API ({model_name}) を呼び出し中 [provider: {provider}]...")
        return llm_chat(model_name, messages, options, storage_path)
    except ValueError as error:
        print(f"⚠️ モデル '{model_name}' が models_config.json に登録されていません: {error}")
        return None

def main():
    load_env()
    parser = argparse.ArgumentParser(description="時間帯動的対応ニュース日記自動生成スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="Gitへのプッシュを行わずに実行します")
    parser.add_argument("--hour-mock", type=int, help="時間帯判定のテスト用に時刻（時）を偽装します")
    parser.add_argument("--model", type=str, default=None, help="使用するモデル名 (models_config.json のキー)。デフォルトは gemma4:31b-cloud です")
    parser.add_argument("--models-config", type=str, default=None, help="models_config.json のパス。未指定時は llm_manager が自動解決します")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        print("❌ エラー: 環境変数 GEMINI_API_KEY が設定されていません。（フォールバック用）")
        sys.exit(1)

    models_config_path = args.models_config or os.environ.get("LLM_MODELS_CONFIG")
    model_name = (
        args.model
        or os.environ.get("LLM_MODEL")
        or os.environ.get("GEMINI_MODEL")
        or DEFAULT_MODEL
    )
    fallback_model = (
        os.environ.get("LLM_FALLBACK_MODEL")
        or os.environ.get("GEMINI_FALLBACK_MODEL")
        or DEFAULT_FALLBACK_MODEL
    )

    # 時刻判定と動的パラメータの算出
    now_jst = datetime.now(JST)
    hour = args.hour_mock if args.hour_mock is not None else now_jst.hour
    minute = 0 if args.hour_mock is not None else now_jst.minute
    
    time_str = f"{hour}時{f'{minute:02d}分' if minute > 0 else ''}"
    
    if 5 <= hour < 12:
        time_of_day = "朝"
        greeting = f"ご主人様、おはようございます！現在朝の {time_str}になりましたわ！🐾"
        title_prefix = "📢 朝のニュース日記："
        closing = "今日も一日、元気にいきましょう！🐾"
    elif 12 <= hour < 18:
        time_of_day = "昼"
        greeting = f"ご主人様、お昼になりましたわ！現在 {time_str}になりましたわ！🐾"
        title_prefix = "📢 昼のニュース日記："
        closing = "午後もご主人様を応援しておりますわ！🐾"
    else:
        time_of_day = "夜"
        greeting = f"ご主人様、夜の {time_str}になりましたわ！🐾"
        title_prefix = "📢 夜のニュース日記："
        closing = "今夜も温かくしておやすみなさいませ。🐾"

    # 公開日時のフォーマット
    if args.hour_mock is not None:
        published_dt = now_jst.replace(hour=hour, minute=minute, second=0, microsecond=0)
        published_at = published_dt.isoformat()
    else:
        published_at = now_jst.isoformat()

    # 処理開始前にリモートに追いつく
    if not args.dry_run:
        print("🐾 リモートから最新情報を取得中 (git pull --rebase)...")
        try:
            branch_res = subprocess.run(
                ["git", "branch", "--show-current"], capture_output=True, text=True, encoding="utf-8", cwd=BASE_DIR
            )
            branch_name = branch_res.stdout.strip() or "main"
            subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", branch_name], check=True, cwd=BASE_DIR
            )
            print("🐾 リモートの最新情報を取得しました。")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ 警告: git pull に失敗しました。競合があるか、またはオフライン環境の可能性があります: {e}")

    print(f"🐾 {time_of_day}のニュース日記の自動生成を開始します。")

    # 1. ニュース候補の収集（重複・48時間超過を事前除外）
    unique_candidates = collect_candidates(FEEDS, get_recent_titles(os.path.join(BASE_DIR, "news.json")))

    print(f"🐾 投稿可能な候補ニュースを {len(unique_candidates)} 件検出しました。")
    if not unique_candidates:
        print("⚠️ 新規に配信できる AI ニュース候補がありません。直近記事と重複しているか、RSS に新着がない可能性があります。")
        sys.exit(0)

    # 2. 直近記事タイトルの取得
    news_json_path = os.path.join(BASE_DIR, "news.json")
    recent_titles = get_recent_titles(news_json_path)

    # 3. 日付の設定
    execution_date = now_jst.strftime("%Y-%m-%d")

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
        "published_at": published_at,
        "time_of_day": time_of_day,
        "greeting": greeting,
        "title_prefix": title_prefix,
        "closing": closing,
        "recent_titles": recent_titles[:15],
        "news_candidates": unique_candidates[:8]
    }
    user_content = json.dumps(context, ensure_ascii=False, indent=2)

    # 6. LLM API の呼び出し (llm_manager 経由)
    use_ollama_primary = is_ollama_model(model_name, models_config_path)
    response_text = call_llm_api(model_name, system_prompt, user_content, models_config_path)
    if not response_text and fallback_model != model_name:
        print(f"🐾 {model_name} が利用できないため {fallback_model} にフォールバックします...")
        response_text = call_llm_api(fallback_model, system_prompt, user_content, models_config_path)
        use_ollama_primary = False

    if not response_text:
        print(f"❌ エラー: {model_name} からの応答の取得に失敗しました。")
        sys.exit(1)

    # 7. 応答のパースと検証
    def load_article_response(raw_text, source_model, allow_fallback_retry=True):
        try:
            return parse_article_json(raw_text)
        except json.JSONDecodeError:
            if allow_fallback_retry and use_ollama_primary and fallback_model != model_name:
                print(f"⚠️ {source_model} の JSON パースに失敗しました。{fallback_model} で再試行します...")
                fallback_text = call_llm_api(fallback_model, system_prompt, user_content, models_config_path)
                if fallback_text:
                    return load_article_response(fallback_text, fallback_model, allow_fallback_retry=False)
            print(f"❌ エラー: {source_model} の応答が有効な JSON ではありません。")
            print(raw_text)
            sys.exit(1)

    article_data, _ = load_article_response(response_text, model_name)

    # エラーレスポンスのチェック（フォールバックモデルへ再試行）
    if "error" in article_data:
        if article_data.get("error") == "NO_VERIFIED_NEWS" and use_ollama_primary and fallback_model != model_name:
            print(f"⚠️ プライマリモデルが候補なしと判断しました: {article_data.get('message', '理由不明')}")
            print(f"🐾 {fallback_model} で再試行します...")
            fallback_text = call_llm_api(fallback_model, system_prompt, user_content, models_config_path)
            if fallback_text:
                article_data, _ = load_article_response(fallback_text, fallback_model, allow_fallback_retry=False)
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
            commit_msg = f"feat: {time_of_day}のニュース日記自動配信（{execution_date}）🐾"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=BASE_DIR)
            # ビルド中にリモートが進んでいる場合に備え、プッシュ前に再度同期
            branch_res = subprocess.run(
                ["git", "branch", "--show-current"], capture_output=True, text=True, encoding="utf-8", cwd=BASE_DIR
            )
            branch_name = branch_res.stdout.strip() or "main"
            subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", branch_name], check=True, cwd=BASE_DIR
            )
            subprocess.run(["git", "push", "-u", "origin", branch_name], check=True, cwd=BASE_DIR)
            print("🐾 Git へのプッシュが完了しました！ブログがデプロイされますわ。")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ 警告: Git へのコミット・プッシュ中にエラーが発生しました。認証設定等を確認してください: {e}")

    print("🐾 すべての処理が正常に完了しました！")

if __name__ == "__main__":
    main()
