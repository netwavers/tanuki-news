import os
import sys
import re
import json
import html
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

# 標準出力をUTF-8に設定
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 定数定義
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(BASE_DIR, "articles")

from llm_client import DEFAULT_COMMENT_MODEL, build_chat_options, chat as llm_chat, get_llm_client
TEMPLATE_PATH = os.path.join(ARTICLES_DIR, "template.html")
NEWS_JSON_PATH = os.path.join(BASE_DIR, "news.json")
RSS_XML_PATH = os.path.join(BASE_DIR, "rss.xml")

# ==========================================================================
# Markdown -> HTML parser
# ==========================================================================
def simple_markdown_to_html(md_text):
    """標準の正規表現を用いた簡易Markdown->HTMLコンバーター"""
    # エスケープされたアスタリスクの処理
    text = md_text.replace(r"\*\*", "STARS_PLACEHOLDER")
    
    # 段落分けと改行の基本処理
    lines = text.split('\n')
    html_lines = []
    in_list = False
    in_quote = False
    
    for line in lines:
        line_str = line.strip()
        
        # リストの閉じ処理
        if not (line_str.startswith('*') or line_str.startswith('-')) and in_list:
            html_lines.append("</ul>")
            in_list = False
            
        # 引用の閉じ処理
        if not line_str.startswith('>') and in_quote:
            html_lines.append("</blockquote>")
            in_quote = False

        if not line_str:
            html_lines.append("<br>")
            continue

        # ヘッダー (###, ##, #)
        if line_str.startswith('###'):
            header_text = line_str[3:].strip()
            header_text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'\1\2', header_text)
            html_lines.append(f"<h3>{header_text}</h3>")
        elif line_str.startswith('##'):
            header_text = line_str[2:].strip()
            header_text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'\1\2', header_text)
            html_lines.append(f"<h2>{header_text}</h2>")
        elif line_str.startswith('#'):
            header_text = line_str[1:].strip()
            header_text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'\1\2', header_text)
            html_lines.append(f"<h1>{header_text}</h1>")
            
        # 引用 (>)
        elif line_str.startswith('>'):
            quote_text = line_str[1:].strip()
            # GitHubスタイルのアラートチェック
            if quote_text.startswith('[!NOTE]'):
                html_lines.append("<blockquote class='alert alert-note'>")
                in_quote = True
                continue
            elif quote_text.startswith('[!WARNING]'):
                html_lines.append("<blockquote class='alert alert-warning'>")
                in_quote = True
                continue
            
            if not in_quote:
                html_lines.append("<blockquote>")
                in_quote = True
            
            # ボールド処理
            quote_text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'<strong>\1\2</strong>', quote_text)
            html_lines.append(f"<p>{quote_text}</p>")
            
        # 箇条書きリスト (*, -)
        elif line_str.startswith('*') or line_str.startswith('-'):
            # 行頭が太字のマーカーで始まっている場合は、リストではなく単なる太字段落として処理する
            if line_str.startswith('**') or line_str.startswith('__'):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                para_text = line_str
                para_text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'<strong>\1\2</strong>', para_text)
                html_lines.append(f"<p>{para_text}</p>")
            else:
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                list_item = re.sub(r'^[*+-]\s*', '', line_str)
                list_item = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'<strong>\1\2</strong>', list_item)
                html_lines.append(f"<li>{list_item}</li>")
            
        # 一般段落
        else:
            para_text = line_str
            para_text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'<strong>\1\2</strong>', para_text)
            html_lines.append(f"<p>{para_text}</p>")
            
    # 開きっぱなしのタグを閉じる
    if in_list:
        html_lines.append("</ul>")
    if in_quote:
        html_lines.append("</blockquote>")

    result = '\n'.join(html_lines)
    # プレースホルダーを太字タグに戻す
    result = result.replace("STARS_PLACEHOLDER", "<strong>*</strong>")
    return result

def parse_markdown_article(file_path):
    """Markdownファイルからタイトル、日付、概要、本文を抽出する（frontmatter対応）"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Frontmatter (YAML風) の抽出と除去
    frontmatter = {}
    body = content
    if content.strip().startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    k, v = [x.strip() for x in line.split(":", 1)]
                    frontmatter[k] = v.strip('"').strip("'")
            body = parts[2].strip()

    # タイトルの抽出（frontmatter優先）
    title = frontmatter.get("title", "")
    if not title:
        title_match = re.search(r"^###\s+\*\*(.*?) \*\*|^#\s+(.*)", body, re.MULTILINE)
        if title_match:
            title = title_match.group(1) or title_match.group(2)
        else:
            title = os.path.splitext(os.path.basename(file_path))[0]
    title = title.strip()

    # 概要の抽出（frontmatter優先）
    description = frontmatter.get("description", "")
    if not description:
        desc_match = re.search(r"\*\*【概要】\*\*(.*?)(?=###|\n\n\w|$)", body, re.DOTALL | re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip()
            description = re.sub(r"\*\*|__", "", description)
        else:
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
            for p in paragraphs:
                if not p.startswith("#") and not p.startswith("ご主人様"):
                    description = p[:150]
                    break
    description = html.escape(description)

    # 日付の抽出（frontmatter優先）
    pub_date = frontmatter.get("published_at", "")
    if not pub_date:
        pub_date = datetime.utcnow().isoformat() + "Z"
        date_match = re.search(r"本日（(\d{4})年(\d{1,2})月(\d{1,2})日）", body)
        if date_match:
            try:
                year, month, day = map(int, date_match.groups())
                dt = datetime(year, month, day, 6, 0, 0)
                pub_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass

    return {
        "title": title,
        "description": description,
        "published_at": pub_date,
        "raw_content": body,
        "frontmatter": frontmatter
    }



def generate_ai_comment_from_content(title, full_content, category):
    """llm_manager 経由で、Markdownからたぬきちゃんのまとめ用一言コメントを自動生成"""
    if not os.environ.get("GEMINI_API_KEY"):
        paragraphs = [p.strip() for p in full_content.split('\n\n') if p.strip()]
        fallback_comment = ""
        for p in paragraphs:
            if "**【概要】**" in p:
                clean_p = p.replace("**【概要】**", "").strip()
                sentences = re.split(r'[。！!？?]', clean_p)
                if sentences and sentences[0]:
                    fallback_comment = sentences[0] + "！🐾"
                    break
        if not fallback_comment:
            fallback_comment = f"ご主人様、この記事は要チェックですわ！「{title}」についての詳細、必見ですの！🐾"
        return fallback_comment

    prompt = f"""
あなたはご主人様に仕えるメイドさん風AIアシスタントの「たぬきちゃん」です。
以下の記事全体を読んで、まとめサイトのカードに表示する、メイドさんらしい丁寧で愛嬌のあるイチオシ紹介コメント（日本語、1〜2文程度、120文字以内）を書いてください。
「ご主人様！〜〜ですわ！」や「〜〜ですね！」といった愛嬌のある話し方を好みます。

記事本文:
{full_content}

コメントのみをそのまま出力してください。前置きや解説などは一切不要です。たぬきちゃんの発言そのものだけを出力してください。
"""
    try:
        client = get_llm_client(DEFAULT_COMMENT_MODEL)
        options = build_chat_options(client.config.provider.value, temperature=0.8, max_output_tokens=200)
        comment = llm_chat(DEFAULT_COMMENT_MODEL, [{"role": "user", "content": prompt}], options)
        if comment:
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1]
            return comment
    except Exception as e:
        print(f"⚠️ LLM APIコメント自動生成エラー: {e}")
    return f"ご主人様！こちらの「{title}」について、たぬきちゃんも超イチオシですわ！🐾"

# ==========================================================================
# HTML parser & cleaner (for raw HTML files like rtx_3060.html)
# ==========================================================================
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_html_tags(html_content):
    """HTMLからスクリプト、スタイル、およびタグを除去してプレーンテキストを抽出する"""
    # script と style タグの中身を除去
    clean_content = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', ' ', html_content, flags=re.IGNORECASE)
    clean_content = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', ' ', clean_content, flags=re.IGNORECASE)
    # コメント行を除去
    clean_content = re.sub(r'<!--.*?-->', ' ', clean_content, flags=re.DOTALL)
    
    # タグの除去
    s = MLStripper()
    s.feed(clean_content)
    return s.get_data()

def parse_html_article(file_path):
    """HTMLファイルからタイトル、日付、概要、プレーンテキスト本文を抽出する"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # タイトル (<title>タグ)
    title = "無題のHTML記事"
    title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = html.unescape(title_match.group(1).strip())
    else:
        title = os.path.splitext(os.path.basename(file_path))[0]
    
    # 日付 (ファイルの更新日時をベースにし、本文中に日付があれば優先)
    mtime = os.path.getmtime(file_path)
    pub_date = datetime.fromtimestamp(mtime).isoformat() + "Z"
    
    # 本文中の日付パターン検索 (例: 2026年6月17日)
    date_match = re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日', content)
    if date_match:
        try:
            year, month, day = map(int, date_match.groups())
            dt = datetime(year, month, day, 12, 0, 0)
            pub_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    # <body> 内の中身をプレーンテキスト化
    body_content = content
    body_match = re.search(r'<body[^>]*>(.*?)</body>', content, re.IGNORECASE | re.DOTALL)
    if body_match:
        body_content = body_match.group(1)
        
    plain_text = strip_html_tags(body_content)
    plain_text = re.sub(r'\s+', ' ', plain_text).strip()
    
    # 概要のフォールバック (先頭120文字)
    description = plain_text[:120] + "..." if len(plain_text) > 120 else plain_text

    return {
        "title": title,
        "description": description,
        "published_at": pub_date,
        "plain_text": plain_text
    }

def get_ai_metadata_for_html(title, plain_text, category):
    """llm_manager 経由で、HTML記事からタイトル、概要、およびコメントをJSONとして自動抽出。キー未設定時はフォールバック。"""
    fallback_data = {
        "title": title,
        "description": plain_text[:120] + "..." if len(plain_text) > 120 else plain_text,
        "comment": f"ご主人様！こちらの「{title}」について、たぬきちゃんも超イチオシですわ！🐾"
    }
    
    if not os.environ.get("GEMINI_API_KEY"):
        return fallback_data

    prompt = f"""
あなたはご主人様に仕えるメイドさん風AIアシスタントの「たぬきちゃん」です。
提供された以下の記事テキスト（HTMLからタグを剥がしたもの）を読み、まとめサイトに掲載するための：
1. タイトル（適切な短い日本語タイトル、元のタイトルに合わせる）
2. 概要（記事の要点、日本語、120文字程度）
3. たぬきちゃん風の紹介コメント（メイドさんらしい丁寧で愛嬌のあるもの、日本語、120文字以内）
を抽出・生成してください。

記事テキスト:
{plain_text[:4000]}

以下のJSONフォーマットのみで厳密に出力してください。他の文章や ```json マークダウンなどの装飾は一切出力しないでください：
{{
  "title": "タイトル",
  "description": "概要",
  "comment": "コメント"
}}
"""
    
    try:
        client = get_llm_client(DEFAULT_COMMENT_MODEL)
        options = build_chat_options(client.config.provider.value, json_mode=True, temperature=0.8, max_output_tokens=300)
        result_text = llm_chat(DEFAULT_COMMENT_MODEL, [{"role": "user", "content": prompt}], options)
        if not result_text:
            return fallback_data

        if "```" in result_text:
            result_text = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', result_text, flags=re.DOTALL).strip()

        parsed_json = json.loads(result_text)
        return {
            "title": parsed_json.get("title", title).strip(),
            "description": parsed_json.get("description", fallback_data["description"]).strip(),
            "comment": parsed_json.get("comment", fallback_data["comment"]).strip()
        }
    except Exception as e:
        print(f"⚠️ LLM HTML解析エラー: {e}")
        return fallback_data

# ==========================================================================
# Main Build Loop
# ==========================================================================
def build_articles():
    print("🐾 記事のビルド処理を開始します...")
    
    # news.json の読み込み
    existing_news = []
    if os.path.exists(NEWS_JSON_PATH):
        try:
            with open(NEWS_JSON_PATH, "r", encoding="utf-8") as f:
                existing_news = json.load(f)
        except Exception as e:
            print(f"⚠️ news.json の読み込みエラー: {e}")

    news_by_url = {item["url"]: item for item in existing_news}

    # articles/ 内の全ファイルをスキャン
    all_files = os.listdir(ARTICLES_DIR)
    
    built_count = 0
    for filename in all_files:
        file_path = os.path.join(ARTICLES_DIR, filename)
        rel_url = f"articles/{filename}"
        
        # テンプレート自体はスキップ
        if filename == "template.html" or filename == "template.md":
            continue

        # Legacy .md をスキップ（JSON形式に統一済み）
        if filename.endswith(".md"):
            print(f"⚠️ レガシー .md をスキップします（JSON形式に統一してください）: {filename}")
            continue

        # テンプレート系をスキップ
        if filename.startswith("_template") or filename == "template.json":
            continue

        # 1. JSON 記事のビルド（統一フォーマット）
        if filename.endswith(".json"):
            print(f"🐾 JSON記事を処理中: {filename}")
            
            with open(file_path, "r", encoding="utf-8") as f:
                article_json = json.load(f)
            
            title = article_json.get("title", filename)
            published_at = article_json.get("published_at", "")
            category = article_json.get("category", "AI")
            score = int(article_json.get("score", 5))
            description = article_json.get("description", "")
            source_type = article_json.get("source_type", "local")
            content_md = article_json.get("content", "")
            
            # テンプレートの読み込み
            if not os.path.exists(TEMPLATE_PATH):
                print(f"⚠️ テンプレートファイルが見つかりません: {TEMPLATE_PATH}")
                continue
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                template_html = f.read()

            # コメントはJSONにあればそれを使い、なければ生成
            if article_json.get("comment"):
                comment = article_json["comment"]
            else:
                comment = generate_ai_comment_from_content(title, content_md, category)
            
            html_content = simple_markdown_to_html(content_md)

            # テンプレートに流し込む
            full_html = template_html
            full_html = full_html.replace("{{TITLE}}", title)
            full_html = full_html.replace("{{DESCRIPTION}}", description[:120] if description else "")
            full_html = full_html.replace("{{PUB_DATE}}", published_at)
            full_html = full_html.replace("{{CATEGORY}}", category)
            full_html = full_html.replace("{{SOURCE}}", "たぬきちゃん")
            full_html = full_html.replace("{{COMMENT}}", comment)
            full_html = full_html.replace("{{CONTENT}}", html_content)

            # HTML詳細ページ書き出し
            html_filename = os.path.splitext(filename)[0] + ".html"
            html_path = os.path.join(ARTICLES_DIR, html_filename)
            rel_html_url = f"articles/{html_filename}"

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(full_html)
                
            news_by_url[rel_html_url] = {
                "title": title,
                "url": rel_html_url,
                "source": "たぬきちゃん",
                "category": category,
                "published_at": published_at,
                "comment": comment,
                "score": score,
                "source_type": source_type
            }
            built_count += 1
            print(f"🐾 HTMLを自動生成しました: {html_filename}")
        # 2. HTML 記事の直接パースとマージ (rtx_3060.html など)
        elif filename.endswith(".html"):
            # 自動生成されたHTML詳細ページはスキップ
            # (対応する .json がある場合は自動生成HTMLなのでスキップ)
            corresponding_json = filename.replace(".html", ".json")
            if os.path.exists(os.path.join(ARTICLES_DIR, corresponding_json)):
                continue
                
            print(f"🐾 HTML記事を直接処理中: {filename}")
            
            html_data = parse_html_article(file_path)
            
            # カテゴリ決定
            category = "IT"
            title_upper = html_data["title"].upper()
            content_upper = html_data["plain_text"].upper()
            if "AI" in title_upper or "LLM" in title_upper or "推論エンジン" in title_upper or "人工知能" in html_data["title"] or "AI" in content_upper:
                category = "AI"
            elif "ガジェット" in html_data["title"] or "スマホ" in title_upper or "GPU" in title_upper or "RTX" in title_upper or "RTX" in content_upper:
                category = "ガジェット"

            # AI解析でメタデータ（一言コメント含む）を最適化生成
            meta = get_ai_metadata_for_html(html_data["title"], html_data["plain_text"], category)
            
            news_by_url[rel_url] = {
                "title": meta["title"],
                "url": rel_url,
                "source": "たぬきちゃん",
                "category": category,
                "published_at": html_data["published_at"],
                "comment": meta["comment"],
                "score": 5
            }
            built_count += 1
            print(f"🐾 HTMLメタデータをマージしました: {filename} (コメント: {meta['comment'][:30]}...)")

    # ソートして news.json に書き戻す (published_at降順)
    updated_news = list(news_by_url.values())
    
    def get_sort_key(item):
        date_str = item.get("published_at", "")
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            try:
                import email.utils
                return email.utils.parsedate_to_datetime(date_str).timestamp()
            except Exception:
                return 0

    updated_news.sort(key=get_sort_key, reverse=True)
    
    # 保存
    with open(NEWS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(updated_news[:60], f, ensure_ascii=False, indent=2)
        
    print(f"🐾 news.json の更新完了しました。(全更新件数: {built_count} 件)")
    
    # RSSの生成
    generate_rss(updated_news[:30])

def generate_rss(news_list):
    """news.jsonのデータから rss.xml を生成する"""
    print("🐾 rss.xml の生成を開始します...")
    
    now_rfc822 = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    rss_items = []
    for item in news_list:
        link = item["url"]
        if not link.startswith("http"):
            link = f"https://netwavers.github.io/tanuki-news/{link}"
            
        pub_date_rfc822 = item["published_at"]
        try:
            dt = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            pub_date_rfc822 = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
        except Exception:
            pass
            
        description_content = f"【たぬきちゃんのコメント】 {item.get('comment', '')}"
        
        rss_item = f"""    <item>
      <title>{html.escape(item['title'])}</title>
      <link>{html.escape(link)}</link>
      <guid isPermaLink="true">{html.escape(link)}</guid>
      <pubDate>{pub_date_rfc822}</pubDate>
      <description><![CDATA[{description_content}]]></description>
      <category>{html.escape(item['category'])}</category>
    </item>"""
        rss_items.append(rss_item)

    rss_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>たぬきちゃんのイチオシニュース</title>
    <link>https://netwavers.github.io/tanuki-news/index.html</link>
    <description>ご主人様にお届けする、今日の厳選IT・AI・ガジェットニュースですわ！🐾</description>
    <language>ja</language>
    <lastBuildDate>{now_rfc822}</lastBuildDate>
    <atom:link href="https://netwavers.github.io/tanuki-news/rss.xml" rel="self" type="application/rss+xml" />
{chr(10).join(rss_items)}
  </channel>
</rss>"""

    with open(RSS_XML_PATH, "w", encoding="utf-8") as f:
        f.write(rss_content)
        
    print("🐾 rss.xml の書き出しに成功しました！")

if __name__ == "__main__":
    build_articles()
