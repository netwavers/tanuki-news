import os
import sys
import re
import json
import html
import urllib.request
from datetime import datetime

# 標準出力をUTF-8に設定
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 定数定義
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTICLES_DIR = os.path.join(BASE_DIR, "articles")
TEMPLATE_PATH = os.path.join(ARTICLES_DIR, "template.html")
NEWS_JSON_PATH = os.path.join(BASE_DIR, "news.json")
RSS_XML_PATH = os.path.join(BASE_DIR, "rss.xml")

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
            # 太字のマーカー除去など
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
    """Markdownファイルからタイトル、日付、概要、本文を抽出する"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # タイトルの抽出（最初の ### **タイトル** や # タイトル）
    title = ""
    title_match = re.search(r'^###\s+\*\*(.*?)\*\*|^#\s+(.*)', content, re.MULTILINE)
    if title_match:
        title = title_match.group(1) or title_match.group(2)
    else:
        # ファイル名から取得（拡張子除く）
        title = os.path.splitext(os.path.basename(file_path))[0]
        
    title = title.strip()

    # 概要の抽出 (**【概要】** から次の見出し ### もしくは空行まで)
    description = ""
    desc_match = re.search(r'\*\*【概要】\*\*(.*?)(?=###|\n\n\w|$)', content, re.DOTALL | re.MULTILINE)
    if desc_match:
        description = desc_match.group(1).strip()
        # 太字等のマークアップ除去
        description = re.sub(r'\*\*|__', '', description)
    else:
        # 最初の段落を概要とする
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        for p in paragraphs:
            if not p.startswith('#') and not p.startswith('ご主人様'):
                description = p[:150]
                break
                
    description = html.escape(description)

    # 日付の抽出（本文中の「本日（YYYY年MM月DD日）」など）
    pub_date = datetime.utcnow().isoformat() + "Z" # デフォルトは現在UTC
    date_match = re.search(r'本日（(\d{4})年(\d{1,2})月(\d{1,2})日）', content)
    if date_match:
        try:
            year, month, day = map(int, date_match.groups())
            dt = datetime(year, month, day, 6, 0, 0) # 朝6時公開とする
            pub_date = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    return {
        "title": title,
        "description": description,
        "published_at": pub_date,
        "raw_content": content
    }

def generate_ai_comment_from_content(title, full_content, category):
    """Gemini APIを叩いて、Markdown全体からたぬきちゃんのまとめ用一言コメントを自動生成。APIキーがない場合は概要から抽出。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        # 概要の最初の1文を抽出するフォールバック
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

    # Gemini APIでコメント生成
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = f"""
あなたはご主人様に仕えるメイドさん風AIアシスタントの「たぬきちゃん」です。
以下の記事全体を読んで、まとめサイトのカードに表示する、メイドさんらしい丁寧で愛嬌のあるイチオシ紹介コメント（日本語、1〜2文程度、120文字以内）を書いてください。
「ご主人様！〜〜ですわ！」や「〜〜ですね！」といった愛嬌のある話し方を好みます。

記事本文:
{full_content}

コメントのみをそのまま出力してください。前置きや解説などは一切不要です。
"""
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 200
        }
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            comment = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1]
            return comment
    except Exception as e:
        print(f"⚠️ Gemini APIコメント自動生成エラー: {e}")
        return f"ご主人様！こちらの「{title}」について、たぬきちゃんも超イチオシですわ！🐾"

def build_articles():
    print("🐾 Markdown記事のビルドを開始します...")
    
    if not os.path.exists(TEMPLATE_PATH):
        print(f"⚠️ テンプレートファイルが見つかりません: {TEMPLATE_PATH}")
        return

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_html = f.read()

    # news.json の読み込み
    existing_news = []
    if os.path.exists(NEWS_JSON_PATH):
        try:
            with open(NEWS_JSON_PATH, "r", encoding="utf-8") as f:
                existing_news = json.load(f)
        except Exception as e:
            print(f"⚠️ news.json の読み込みエラー: {e}")

    news_by_url = {item["url"]: item for item in existing_news}

    # articles/*.md のスキャン
    md_files = [f for f in os.listdir(ARTICLES_DIR) if f.endswith(".md") and f != "template.md"]
    
    built_count = 0
    for md_file in md_files:
        md_path = os.path.join(ARTICLES_DIR, md_file)
        html_filename = os.path.splitext(md_file)[0] + ".html"
        html_path = os.path.join(ARTICLES_DIR, html_filename)
        rel_html_url = f"articles/{html_filename}"
        
        print(f"🐾 記事処理中: {md_file}")
        
        # パース
        article_data = parse_markdown_article(md_path)
        
        # カテゴリの自動決定 (AI, IT, ガジェット, その他)
        category = "IT"
        title_upper = article_data["title"].upper()
        content_upper = article_data["raw_content"].upper()
        if "AI" in title_upper or "LLM" in title_upper or "推論エンジン" in title_upper or "人工知能" in article_data["title"]:
            category = "AI"
        elif "ガジェット" in article_data["title"] or "スマホ" in title_upper or "GPU" in title_upper or "RTX" in title_upper:
            category = "ガジェット"

        # たぬきコメントの生成
        comment = generate_ai_comment_from_content(article_data["title"], article_data["raw_content"], category)
        
        # MarkdownからHTMLへの変換
        html_content = simple_markdown_to_html(article_data["raw_content"])
        
        # テンプレートに流し込む
        full_html = template_html
        full_html = full_html.replace("{{TITLE}}", article_data["title"])
        full_html = full_html.replace("{{DESCRIPTION}}", article_data["description"][:120])
        full_html = full_html.replace("{{PUB_DATE}}", article_data["published_at"])
        full_html = full_html.replace("{{CATEGORY}}", category)
        full_html = full_html.replace("{{SOURCE}}", "たぬきちゃん")
        full_html = full_html.replace("{{COMMENT}}", comment)
        full_html = full_html.replace("{{CONTENT}}", html_content)
        
        # HTML保存
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(full_html)
            
        # news.json用のデータオブジェクト
        news_item = {
            "title": article_data["title"],
            "url": rel_html_url,
            "source": "たぬきちゃん",
            "category": category,
            "published_at": article_data["published_at"],
            "comment": comment,
            "score": 5 # 自作イチオシは最高評価5
        }
        
        # JSONデータの更新（重複は上書き、新規は追加）
        news_by_url[rel_html_url] = news_item
        built_count += 1
        print(f"🐾 HTMLを生成しました: {html_filename}")

    # ソートして news.json に書き戻す (published_at降順)
    updated_news = list(news_by_url.values())
    
    # 日付パース用の補助関数
    def get_sort_key(item):
        date_str = item.get("published_at", "")
        # RFC 2822 もしくは ISO フォーマットのパース
        try:
            # ISO 8601
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            try:
                # RFC 2822 (ZennなどのRSS用)
                # 例: Mon, 15 Jun 2026 16:50:48 GMT
                import email.utils
                return email.utils.parsedate_to_datetime(date_str).timestamp()
            except Exception:
                return 0

    updated_news.sort(key=get_sort_key, reverse=True)
    
    # 保存
    with open(NEWS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(updated_news[:60], f, ensure_ascii=False, indent=2) # 最大60件保存
        
    print(f"🐾 news.json の更新完了しました。(更新件数: {built_count} 件)")
    
    # RSSの生成
    generate_rss(updated_news[:30])

def generate_rss(news_list):
    """news.jsonのデータから rss.xml を生成する"""
    print("🐾 rss.xml の生成を開始します...")
    
    now_rfc822 = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    rss_items = []
    for item in news_list:
        # パス調整
        link = item["url"]
        if not link.startswith("http"):
            # 相対パスの場合は GitHub Pages の本番URLにする
            link = f"https://netwavers.github.io/tanuki-news/{link}"
            
        # 日付のフォーマット変換 (RFC 822)
        pub_date_rfc822 = item["published_at"]
        try:
            # ISOフォーマットだったら変換する
            dt = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            pub_date_rfc822 = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
        except Exception:
            pass # すでにRFC822などの場合はそのまま
            
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
