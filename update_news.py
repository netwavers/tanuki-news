import os
import sys
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import html
from datetime import datetime

# 標準出力をUTF-8に設定
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# RSSフィード設定
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

def fetch_news_from_rss(feed_info):
    url = feed_info["url"]
    category = feed_info["category"]
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
        
        # Namespaceのハンドリング
        namespaces = {
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'rss': 'http://purl.org/rss/1.0/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'atom': 'http://www.w3.org/2005/Atom'
        }
        
        # item要素の抽出
        items = root.findall('.//item')
        if not items:
            items = root.findall('.//{http://purl.org/rss/1.0/}item')
        if not items:
            items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
            
        news_items = []
        for item in items[:8]:  # 各フィード上位8件
            title_el = item.find('title')
            if title_el is None or not title_el.text:
                continue
            title = html.unescape(title_el.text.strip())
            
            link_el = item.find('link')
            link = ""
            if link_el is not None:
                link = link_el.text if link_el.text else link_el.get('href', '')
            
            if not link:
                continue
                
            # 重複フィルタリング用の正規化
            link = link.strip()
            
            pub_date_el = item.find('pubDate')
            if pub_date_el is None:
                pub_date_el = item.find('{http://purl.org/dc/elements/1.1/}date')
            if pub_date_el is None:
                pub_date_el = item.find('{http://www.w3.org/2005/Atom}published')
                
            pub_date = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else datetime.utcnow().isoformat()
            
            # カテゴリ調整（タイトルに「AI」等が含まれていたらAIカテゴリにするなど）
            item_category = category
            if "AI" in title.upper() or "LLM" in title.upper() or "GPT" in title.upper() or "人工知能" in title:
                item_category = "AI"
            elif "ガジェット" in title or "スマホ" in title or "PC" in title or "折りたたみ" in title:
                item_category = "ガジェット"
                
            news_items.append({
                "title": title,
                "url": link,
                "source": source,
                "category": item_category,
                "published_at": pub_date,
                "comment": "",
                "score": 4  # デフォルトおすすめ度
            })
        return news_items
    except Exception as e:
        print(f"⚠️ RSS取得エラー ({url}): {e}")
        return []

def generate_tanuki_comment(title, category):
    """Gemini APIを使用して、たぬきちゃん風のコメントを生成する。APIキーがない場合はフォールバックする。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        # フォールバック用ランダムテンプレート
        import random
        templates = [
            f"ご主人様、こちらの {category} ニュースは要チェックですわ！「{title}」についての動き、これからも目が離せませんね！🐾",
            f"なんと！「{title}」とのことですわ！ご主人様の開発や日々の作業にも、何か新しいひらめきをもたらすかもしれませんね。応援しております！✨",
            f"ご主人様、{category}関連でとても興味深い話題が入ってきました！「{title}」について、たぬきちゃんももっとお勉強しておきますわ！🥯",
            f"ご主人様、お疲れ様です！このニュース、とってもワクワクしますね！美味しいお茶でも飲みながら、ゆっくり読んでみてくださいませ！🍵"
        ]
        return random.choice(templates)

    # Gemini API経由での生成
    # ここではGemini 2.5 Flashを使用します
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    prompt = f"""
あなたはご主人様に仕えるメイドさん風AIアシスタントの「たぬきちゃん」です。
以下のニュース記事に対して、メイドさんらしい丁寧で、ちょっぴりユーモアや愛嬌のあるイチオシ紹介コメント（日本語、1〜2文程度、120文字以内）を書いてください。
「ご主人様！〜〜ですわ！」や「〜〜ですね！」といった愛嬌のある話し方を好みます。

ニュースタイトル: {title}
カテゴリ: {category}

コメントのみをそのまま出力してください。余計なマークダウン装飾（引用符など）や「はい、コメントは以下の通りです」などの前置きは一切不要です。たぬきちゃんの発言そのものだけを出力してください。
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
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            comment = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            # 稀に前後のダブルクォーテーションが入ってしまう場合のトリミング
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1]
            return comment
    except Exception as e:
        print(f"⚠️ Gemini APIコメント生成エラー: {e}")
        # エラー時もフォールバック
        return f"ご主人様！こちらの「{title}」のニュース、とっても気になりますわね！🐾"

def main():
    json_path = os.path.join(os.path.dirname(__file__), "news.json")
    
    # 既存データのロード
    existing_news = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing_news = json.load(f)
        except Exception as e:
            print(f"⚠️ 既存のJSONロードエラー: {e}")
            
    existing_urls = {item["url"] for item in existing_news}
    
    # RSSから新規ニュース取得
    all_fetched_news = []
    for feed in FEEDS:
        all_fetched_news.extend(fetch_news_from_rss(feed))
        
    # 重複排除と新規ニュースの抽出
    new_items = []
    for item in all_fetched_news:
        if item["url"] not in existing_urls:
            new_items.append(item)
            existing_urls.add(item["url"])  # 同一取得内での重複も防ぐ
            
    print(f"🐾 新規ニュースを {len(new_items)} 件検出しました。")
    
    if not new_items:
        print("🐾 新しいニュースはありませんでした。")
        return
        
    # 新規ニュースに対してコメントを生成 (API負荷を考慮し、最大5件程度に制限して追加)
    added_count = 0
    for item in new_items[:5]:  # 一回に最大5件追加
        print(f"🐾 コメント生成中: {item['title']}")
        comment = generate_tanuki_comment(item["title"], item["category"])
        item["comment"] = comment
        
        # 公開日時をISOフォーマットに統一する簡易処理
        # (RSSごとにフォーマットが異なるため)
        # 今回はそのままにするか、フォーマットを少し綺麗にする
        
        existing_news.insert(0, item)  # 先頭（最新）に追加
        added_count += 1
        
    # 最大表示件数を制限（例: 50件）
    updated_news = existing_news[:50]
    
    # JSONファイルへの書き込み
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(updated_news, f, ensure_ascii=False, indent=2)
        print(f"🐾 news.json を更新しました！ ({added_count} 件追加)")
    except Exception as e:
        print(f"⚠️ news.json 書き込みエラー: {e}")

if __name__ == "__main__":
    main()
