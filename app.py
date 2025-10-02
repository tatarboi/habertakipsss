#!/usr/bin/env python3
import threading
import time
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from flask import Flask, render_template, request, jsonify

# Diğer modüllerden importlar
from feeds import RSS_FEEDS
from extractor import extract_image

DB_PATH = 'articles.db'
FETCH_INTERVAL_SECONDS = 60  # 1 dakika
USER_AGENT = 'SamsunRSSBot/2.0 (+https://example.local)'
KEYWORD_TO_SEARCH = 'samsun'  # Ulusal basında aranacak kelime

app = Flask(__name__)


# -------------------------
# OPML Okuyucu (app1.py'den alındı ve geliştirildi)
# -------------------------
def read_opml(file_path="rss.opml"):
    """OPML dosyasını okur ve RSS feed URL'lerini döndürür."""
    urls = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        for outline in root.findall('.//outline[@xmlUrl]'):
            url = outline.attrib.get('xmlUrl')
            if url:
                urls.append(url)
        print(f"✅ {len(urls)} adet ulusal RSS kaynağı OPML dosyasından okundu.")
        return urls
    except Exception as e:
        print(f"⚠️ HATA: OPML dosyası okunurken hata oluştu: {e}")
        return []


NATIONAL_RSS_FEEDS = read_opml()


# -------------------------
# DB helpers
# -------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    # Kategori sütunu ekleniyor
    conn.execute(
        """CREATE TABLE IF NOT EXISTS articles (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               guid TEXT,
               url TEXT UNIQUE,
               title TEXT,
               source TEXT,
               published TIMESTAMP,
               image_url TEXT,
               summary TEXT,
               category TEXT DEFAULT 'yerel',
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    # Geriye dönük uyumluluk için sütun var mı kontrol et, yoksa ekle
    try:
        conn.execute("SELECT category FROM articles LIMIT 1")
    except sqlite3.OperationalError:
        print("Veritabanı şeması güncelleniyor: 'category' sütunu ekleniyor...")
        conn.execute("ALTER TABLE articles ADD COLUMN category TEXT DEFAULT 'yerel'")

    conn.execute('CREATE INDEX IF NOT EXISTS idx_published ON articles(published DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_category ON articles(category)')
    conn.commit()


# -------------------------
# Utilities
# -------------------------
def normalize_url(url: str) -> str:
    # ... (Bu fonksiyon değişmedi)
    try:
        p = urlparse(url)
        qs = [(k, v) for (k, v) in parse_qsl(p.query, keep_blank_values=True)
              if not k.lower().startswith('utm_') and k.lower() not in {'gclid', 'fbclid'}]
        new_query = urlencode(qs)
        cleaned = urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, ''))
        return cleaned
    except Exception:
        return url


def human_source(url: str) -> str:
    # ... (Bu fonksiyon değişmedi)
    try:
        netloc = urlparse(url).netloc
        host = netloc.replace('www.', '')
        return host
    except Exception:
        return 'kaynak'


def to_utc(dt):
    # ... (Bu fonksiyon değişmedi)
    if isinstance(dt, str):
        try:
            dt = dateparser.parse(dt)
        except Exception:
            return None
    if not dt:
        return None
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# -------------------------
# Fetcher (Birleştirilmiş Mantık)
# -------------------------
def process_feed(feed_url: str, category: str, conn):
    """Tek bir RSS kaynağını işler ve veritabanına kaydeder."""
    headers = {'User-Agent': USER_AGENT}
    try:
        feed = feedparser.parse(feed_url, request_headers=headers)
        for e in feed.entries:
            title = getattr(e, 'title', '').strip()
            link = normalize_url(getattr(e, 'link', '').strip())
            summary_html = getattr(e, 'summary', '') or getattr(e, 'description', '')
            summary_text = BeautifulSoup(summary_html, 'html.parser').get_text('\n', strip=True)

            if not link or not title:
                continue

            # Ulusal haberler için anahtar kelime kontrolü
            if category == 'ulusal':
                if KEYWORD_TO_SEARCH not in title.lower() and KEYWORD_TO_SEARCH not in summary_text.lower():
                    continue

            guid = getattr(e, 'id', '') or getattr(e, 'guid', '') or link
            pub = None
            for key in ('published', 'updated', 'created', 'pubDate'):
                if getattr(e, key, None):
                    pub = to_utc(getattr(e, key))
                    if pub: break

            image_url = extract_image(e, fallback_domain=urlparse(link).netloc)
            source = human_source(link)

            try:
                conn.execute(
                    'INSERT OR IGNORE INTO articles (guid, url, title, source, published, image_url, summary, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (guid, link, title, source, pub.isoformat() if pub else None, image_url, summary_text[:600],
                     category)
                )
                # Commit her işlemde değil, kaynak başına yapılırsa daha hızlı olur.
            except sqlite3.Error as db_err:
                print(f"DB Hatası: {db_err}")
                pass
        conn.commit()  # Kaynak bittikten sonra commit et.
    except Exception as fetch_err:
        print(f"Kaynak işlenemedi {feed_url}: {fetch_err}")


def fetch_once():
    conn = get_db()
    print("\n--- Haberler Taranıyor ---")

    print(f"-> {len(RSS_FEEDS)} yerel kaynak işleniyor...")
    for feed_url in RSS_FEEDS:
        process_feed(feed_url, 'yerel', conn)

    print(f"-> {len(NATIONAL_RSS_FEEDS)} ulusal kaynak '{KEYWORD_TO_SEARCH}' için taranıyor...")
    for feed_url in NATIONAL_RSS_FEEDS:
        process_feed(feed_url, 'ulusal', conn)

    print("--- Tarama Tamamlandı ---\n")


def fetch_loop():
    while True:
        try:
            fetch_once()
        except Exception as e:
            print(f"Döngüde hata: {e}")
        time.sleep(FETCH_INTERVAL_SECONDS)


# -------------------------
# Web routes
# -------------------------
@app.route('/')
def index():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 30))
    conn = get_db()

    # Sadece yerel haberlerde arama yapılıyor
    where_sql = "WHERE category = 'yerel'"
    params = []
    if q:
        where_sql += ' AND (title LIKE ? OR summary LIKE ?)'
        like = f'%{q}%'
        params.extend([like, like])

    local_items = conn.execute(
        f'''SELECT * FROM articles {where_sql}
            ORDER BY COALESCE(published, created_at) DESC
            LIMIT ?''', (*params, limit)
    ).fetchall()

    national_items = conn.execute(
        '''SELECT * FROM articles WHERE category = 'ulusal'
           ORDER BY COALESCE(published, created_at) DESC
           LIMIT ?''', (18,)  # Ulusal için limit
    ).fetchall()

    return render_template('index.html', local_items=local_items, national_items=national_items, q=q)


@app.route('/api/articles')
def api_articles():
    """Sonsuz kaydırma SADECE YEREL haberler için çalışır."""
    after = request.args.get('after')
    limit = int(request.args.get('limit', 30))
    conn = get_db()
    params = []
    where = ["category = 'yerel'"]
    if after:
        where.append('COALESCE(published, created_at) < ?')
        params.append(after)

    where_sql = 'WHERE ' + ' AND '.join(where)
    rows = conn.execute(
        f'''SELECT * FROM articles {where_sql}
            ORDER BY COALESCE(published, created_at) DESC
            LIMIT ?''', (*params, limit)
    ).fetchall()
    items = [{k: r[k] for k in r.keys()} for r in rows]
    return jsonify({'items': items})


if __name__ == '__main__':
    import socket

    init_db()
    print("İlk tarama başlatılıyor...")
    fetch_once()

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "localhost"

    print(f"\n✅ Uygulama hazır!")
    print(f"📡 Yerel:   http://127.0.0.1:8000")
    print(f"🌐 Ağdan:   http://{lan_ip}:8000\n")

    t = threading.Thread(target=fetch_loop, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)