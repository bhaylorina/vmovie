import re
import time
import json
import base64
import urllib.parse
import html as html_lib
from datetime import date
from urllib.parse import quote, unquote, urlsplit
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
import requests as std_requests
from flask import Flask, request, redirect, Response

# ================= FIRESTORE SETUP =================
import firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_CREDENTIALS = json.loads(r"""
{
  "type": "service_account",
  "project_id": "movies-d584a",
  "private_key_id": "ae405f74f279a5350f2e162a59d4e51fe81233b8",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC+bteStrCqzpMT\nUv5hHrp/fNMwu7RlJG+0B6EL3Xjx6oil2HDhlvqJWgkX+a8GKeMbLi9ymGJlieUp\njBWa7ZpDReby4O0fZ+I0ZWnxHJNFsK9UUyiH2/JPdk3xHZyLypLBVpRMlAT4Bk9U\nMjipA5cLYCWK5/qkwY7H3vcGmmadXcaACcGyuuqLEGTFRXB3D87h+FcKcdzpNZRi\nv8P3C8FWPFR7kDjZb5G4hvWBH3lQnCPMKkOSiIWrxxyZeUHRwUXdx6g9RciN7hOS\nlHADgvvonZDFruQ3q86mrUoffGBu+dk6CukgPbPs7sevBO6hmzUAsAEPK6ryzTO9\nVnecVg33AgMBAAECggEADMbJBdnl/n+/lGNUF9YE8zq/vJxLXSHVsMF2R6KDU8/F\nfUMJR8lmY8K7q3UgDgzPZOpzWn/o0iEvU9tHM87PM8ZD2XXH0vyYS6WmNvwQ0XMq\nQEEYDg1us3AfiJbRAvwDXp9dccnYj3904RRBgu1vu96mhixMP7OQzc4iyrmfOt2L\nKLwp8RNrdw/T3ovHSgqkG3PhlPbUCorwPuqthRvY0vMHcamAD9xpZgKzRyj7Qf8x\n2KXxI1twJZ7WvDu1rSYTExL2w6No9VZ+hzkWBWnv1nr93L+RW3buJORvzcl2qSeP\n6GXYQUr2nZ60gpVbLraXN5wX6GyRiaNuyAWXzXSGQQKBgQDjicUPwYoMN3CmYek9\nY0INUHTZ8n9+OOfpZiuKc7iLR6LUBXkmocdbU8V8CayjY/haltkQYTDVZukqksaA\nv3E0dIyIjEk1Xj6SdCwe1PqiiAOyAGVDq/DF1jsoYQb4va5o6BZ/MwdXrkycoSlQ\nwncuJGyjPQvt9Xa7J1/lgOsC4QKBgQDWQOO3hHhkJl5sVQ7kFMws7GXo/KzaY0cL\nAJnJ20bBc4GMw5YRf2qoQBIJSChYkyCBbidZ5IPKhgSGi4iqUK65I3q2Ct7Y5GD4\nqfymvQDLd5vFhIUufOzz+zRvSDH1XiQxni5dSNcdgZHM5KUTplRptXgzlH905jm+\nTwcOwa4D1wKBgQDIlfVA1I8MAfuu0XW6Bjx+XEUGtT4rWaMoIEeWADnZnscuPbz1\nj3ydSBY6KJUmXMTdp0mnpOZV2ikGvOl9KkdzxKL25STMhU6H8R3L+FkS2vDXBH5A\nz9yrqxXvnMl2klCkbqUWcTex1hf3pCM17Jj/9mBG71QK7G9EwYtKWQHUQQKBgEPe\nWkQP2nMfFFoMt6LYU7UHTWD4aWjkeeSqVAz1QPyWsjr82dTBH/AcG5qFGQK12F4n\nnp+DG5xTx6s3GBubYz2SV5TC7MSX03/xmO7YgB/zy4xN5kJLoGPI91so62pmX+C3\n0sgKAtp96MmWxBPtZF/39BOivp0xMKlwLzQldhIRAoGAGHqS/sv2gynAJmdad21Q\nvaw9VcjD65PqH+wYoU+Ooy8HUkbruok3yx6TC/KMkmpQK1q0Q+p4bQpHnWj6o/L/\nS7H2ep1Xgi5beWVFmLmC7lp93NLstoS2Xo0ej7q3JxxXkmspzhiZGPuThtTjXjru\nt5/dVEorWabeUNsAzg3cSo8=\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-fbsvc@movies-d584a.iam.gserviceaccount.com",
  "client_id": "112631696952135951671",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40movies-d584a.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
""")

# ✅ FIX: get_app() None return nahi karta, ValueError throw karta hai jab app na ho.
# isliye try/except hi sahi pattern hai (serverless double-init safe).
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(credentials.Certificate(FIREBASE_CREDENTIALS))

db = firestore.client()
COLLECTION = "saved_movies"

def _doc_id(title):
    """Firestore doc ID mein '/' allowed nahi, isliye title ko URL-encode karke safe ID banate hain."""
    return quote(title, safe="")

def fs_get_all():
    """Saari saved movies Firestore se fresh read karta hai. (Koi memory cache nahi = no wipe bug)"""
    result = {}
    try:
        for doc in db.collection(COLLECTION).stream():
            d = doc.to_dict() or {}
            t = d.get("title", "")
            if t:
                result[t] = d
    except Exception as e:
        print(f"[-] Firestore read error: {e}")
    return result

def fs_set(title, data):
    """Sirf EK movie add/update karta hai. Baaki movies ko touch bhi nahi karta."""
    try:
        db.collection(COLLECTION).document(_doc_id(title)).set(data)
        print(f"[+] Firestore me '{title}' save ho gayi!")
    except Exception as e:
        print(f"[-] Firestore save error: {e}")

def fs_delete(title):
    """Sirf EK movie delete karta hai. Empty collection bhi allowed hai (koi placeholder nahi)."""
    try:
        db.collection(COLLECTION).document(_doc_id(title)).delete()
        print(f"[+] Firestore se '{title}' delete ho gayi!")
    except Exception as e:
        print(f"[-] Firestore delete error: {e}")

# ================= FIRESTORE SETUP END =================


app = Flask(__name__)

BASE_URL = "https://new15.hdhub4u.cl"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ⚡ Pre-compiled regex for faster execution in loops
REGEX_PIXELDRAIN = re.compile(r'pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9]+)')
REGEX_R2 = re.compile(r'https?://[a-zA-Z0-9._-]+\.r2\.cloudflarestorage\.com/[^\s"\'<>]+')
REGEX_BASE64_ATOB = re.compile(r"atob\(['\"]([^'\"]+)['\"]\)")
REGEX_BASE64_LONG = re.compile(r'[a-zA-Z0-9+/]{20,}={0,2}')
REGEX_GAME_DRIVE = re.compile(r'https?://(?:pixeldra\.in|pixeldrain\.com|pixeldrain\.net|pixeldrain\.dev)/(?:u|api/file|l)/([^?\s]+)')

# 🔄 Explicit 0 cache TTL for immediate save/delete updates in playlist
CACHE_TTL = 0

# बेस स्क्रिप्ट का स्क्रैपिंग सेशन
session = cffi_requests.Session(impersonate="chrome110")
session.headers.update({
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
})

# सर्च API के लिए अलग सेशन और हेडर्स
API_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": BASE_URL,
    "Referer": BASE_URL + "/",
}
api_session = std_requests.Session()
api_session.headers.update(API_HEADERS)

# Simple In-Memory Cache (sirf m3u ke liye, TTL=0 hone se use nahi hoga)
cache_data = {"m3u": None, "timestamp": 0}

SAVED_DURATION = 3 * 24 * 60 * 60  # 3 दिन

def rot13(s):
    res = []
    for char in s:
        if 'a' <= char <= 'z':
            res.append(chr((ord(char) - ord('a') + 13) % 26 + ord('a')))
        elif 'A' <= char <= 'Z':
            res.append(chr((ord(char) - ord('A') + 13) % 26 + ord('A')))
        else:
            res.append(char)
    return "".join(res)

def decrypt_token(token):
    try:
        s1 = base64.b64decode(token).decode('utf-8')
        s2 = base64.b64decode(s1).decode('utf-8')
        s3 = rot13(s2)
        padded = s3 + "=" * ((4 - len(s3) % 4) % 4)
        s4 = base64.b64decode(padded).decode('utf-8')
        data = json.loads(s4)
        hubcloud_b64 = data.get('o')
        if hubcloud_b64:
            return base64.b64decode(hubcloud_b64).decode('utf-8')
    except Exception:
        pass
    return None

def get_best_link(movie_soup, base_url):
    candidates = []
    for a_tag in movie_soup.find_all('a', href=True):
        text = a_tag.get_text(strip=True)
        if "1080p" in text:
            href = a_tag['href']
            if not href.startswith('http'):
                href = urllib.parse.urljoin(base_url, href)

            size_match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB)', text, re.I)
            size_gb = 0.0
            if size_match:
                val = float(size_match.group(1))
                unit = size_match.group(2).upper()
                size_gb = val / 1024 if unit == 'MB' else val

            if size_gb > 0:
                candidates.append({'href': href, 'text': text, 'size': size_gb})

    if not candidates:
        return None

    def sort_key(c):
        if 2.0 <= c['size'] <= 6.0: return 1
        if c['size'] > 6.0: return 2
        return 3

    candidates.sort(key=sort_key)
    return candidates[0]['href']

def extract_hubcloud_from_gadgets(url):
    try:
        resp = session.get(url, timeout=15)
        token_match = re.search(r"s\('o','([^']+)'", resp.text)
        if token_match:
            hubcloud_url = decrypt_token(token_match.group(1))
            if hubcloud_url:
                if "hblinks" in hubcloud_url:
                    hb_resp = session.get(hubcloud_url, timeout=15)
                    hb_soup = BeautifulSoup(hb_resp.text, 'html.parser')

                    hubdrive_fallback = None
                    for a in hb_soup.find_all('a'):
                        text = a.get_text(strip=True).lower()
                        href = str(a.get('href', '')).lower()

                        if 'hubcloud' in text or 'hubcloud' in href:
                            return a['href']
                        if 'hubdrive' in text or 'hubdrive' in href:
                            hubdrive_fallback = a['href']

                    if hubdrive_fallback:
                        return hubdrive_fallback
                    return None
                return hubcloud_url
    except Exception as e:
        print(f"Gadgets Error: {e}")
    return None

def extract_hubcloud_from_hubdrive(url):
    try:
        resp = session.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.find_all('a'):
            text = a.get_text(strip=True).lower()
            href = str(a.get('href', '')).lower()
            if 'hubcloud' in text or 'hubcloud' in href:
                return a['href']
    except Exception:
        pass
    return None

def convert_pixeldrain_to_direct(url):
    if not url:
        return None

    url = url.replace('&amp;', '&')

    match = REGEX_GAME_DRIVE.search(url)
    if match:
        file_id = match.group(1)
        direct_url = f"https://cdn.pixeldrain.eu.cc/{file_id}"
        print(f"      [🔄] Converted PixelDrain (GameDrive): {direct_url}")
        return direct_url

    return url

def process_hubcloud(hubcloud_url):
    print(f"--> Processing HubCloud: {hubcloud_url}")
    try:
        resp = session.get(hubcloud_url, timeout=15)
        print(f"--> HubCloud Status: {resp.status_code}")
        soup = BeautifulSoup(resp.text, 'html.parser')

        gen_btn = soup.find('a', id='download')
        if not gen_btn:
            for a in soup.find_all('a'):
                text = a.get_text(strip=True).lower()
                if 'generate' in text and 'download' in text:
                    gen_btn = a
                    break

        if not gen_btn or not gen_btn.get('href'):
            print("--> FAILED: Generate button not found (Maybe Cloudflare block).")
            return None

        gen_url = gen_btn['href']
        if not gen_url.startswith('http'):
            gen_url = urllib.parse.urljoin(hubcloud_url, gen_url)

        print(f"--> Clicking Generate: {gen_url}")
        gen_resp = session.get(gen_url, timeout=15)
        print(f"--> Generate Status: {gen_resp.status_code}")

        html_text = gen_resp.text.replace('&amp;', '&').replace('\\u0026', '&').replace('\u0026', '&')
        gen_soup = BeautifulSoup(html_text, 'html.parser')

        # FSL Server Priority
        for a in gen_soup.find_all('a'):
            text = a.get_text(strip=True).lower()
            href = a.get('href', '')
            if 'fsl server' in text and 'fslv2' not in text:
                if href and 'http' in href:
                    print("--> SUCCESS: FSL Link Found!")
                    return href

        all_r2_links = REGEX_R2.findall(html_text)
        valid_r2_links = [l for l in all_r2_links if 't3apac' not in l.lower() and 'fslv2' not in l.lower()]

        if valid_r2_links:
            print("--> SUCCESS: R2 Link Found!")
            for link in valid_r2_links:
                if 'X-Amz-Expires=28800' in link:
                    return link
            return valid_r2_links[0]

        found_links = set()
        for match in REGEX_PIXELDRAIN.finditer(html_text):
            found_links.add(match.group(1))

        for a in gen_soup.find_all('a'):
            for attr in ['data-url', 'data-link', 'data-href', 'data-src']:
                val = a.get(attr)
                if val:
                    for m in REGEX_PIXELDRAIN.finditer(val):
                        found_links.add(m.group(1))

        for match in REGEX_BASE64_LONG.finditer(html_text):
            b64_str = match.group(0)
            try:
                decoded = base64.b64decode(b64_str + "=" * ((4 - len(b64_str) % 4) % 4)).decode('utf-8')
                for m in REGEX_PIXELDRAIN.finditer(decoded):
                    found_links.add(m.group(1))
            except: pass

        for match in REGEX_BASE64_ATOB.finditer(html_text):
            b64_str = match.group(1)
            try:
                decoded = base64.b64decode(b64_str + "=" * ((4 - len(b64_str) % 4) % 4)).decode('utf-8')
                for m in REGEX_PIXELDRAIN.finditer(decoded):
                    found_links.add(m.group(1))
            except: pass

        parsed_url = urllib.parse.urlparse(gen_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        for key, values in query_params.items():
            for val in values:
                try:
                    decoded = base64.b64decode(val + "=" * ((4 - len(val) % 4) % 4)).decode('utf-8')
                    for m in REGEX_PIXELDRAIN.finditer(decoded):
                        found_links.add(m.group(1))
                except: pass
                for m in REGEX_PIXELDRAIN.finditer(val):
                    found_links.add(m.group(1))

        real_ids = [id for id in found_links if id != 'negn6f']
        if real_ids:
            return convert_pixeldrain_to_direct(f"https://pixeldrain.dev/u/{real_ids[0]}")
        elif found_links:
            return convert_pixeldrain_to_direct(f"https://pixeldrain.dev/u/{list(found_links)[0]}")

        print("--> FAILED: FSL, R2 ya PixelDrain link nahi mila.")
        return None
    except Exception as e:
        print(f"HubCloud Error: {e}")
    return None


# ================= सर्च और सेव फंक्शन्स =================

def get_valid_saved():
    """
    Firestore se har baar FRESH read karta hai.
    Expired movies ko individually delete karta hai (bulk overwrite nahi).
    Isliye kabhi poora folder gayab nahi hoga.
    """
    now = time.time()
    all_movies = fs_get_all()
    valid = {}

    for title, data in all_movies.items():
        if isinstance(data, dict) and "saved_at" in data:
            if now - data.get("saved_at", 0) <= SAVED_DURATION:
                valid[title] = data
            else:
                # Sirf expired movie delete, baaki safe
                fs_delete(title)
        else:
            # Invalid entry (jaise purana placeholder) - clean up
            fs_delete(title)

    return valid

def fix_movie_url(url):
    if not url: return ""
    url = url.strip()
    base = urlsplit(BASE_URL)
    if url.startswith("//"): url = "https:" + url
    if not url.startswith("http"): return f"{base.scheme}://{base.netloc}/{url.lstrip('/')}"
    if "hdhub4u" in url.lower() or "hdhub" in url.lower():
        parsed = urlsplit(url)
        return f"{base.scheme}://{base.netloc}{parsed.path}"
    return url

def typesense_search(query):
    today = date.today().isoformat()
    api_url = "https://search.pingora.fyi/collections/post/documents/search"
    params = {
        "q": query, "query_by": "post_title,category,stars,director,imdb_id",
        "query_by_weights": "4,2,2,2,4", "sort_by": "_text_match:desc,sort_by_date:desc",
        "per_page": 50, "highlight_fields": "none", "use_cache": "true", "page": 1, "analytics_tag": today
    }
    for client in (api_session, session):
        try:
            resp = client.get(api_url, params=params, timeout=10)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                results = []
                for hit in hits:
                    doc = hit.get("document", {})
                    title = doc.get("post_title", "")
                    permalink = doc.get("permalink", "")
                    if title and permalink:
                        url = fix_movie_url(permalink)
                        results.append({"title": title, "url": url})
                if results: return results
        except Exception as e:
            print(f"Typesense error: {e}")
    return []

def wp_search(query):
    wp_url = f"{BASE_URL}/wp-json/wp/v2/search"
    for client in (api_session, session):
        try:
            resp = client.get(wp_url, params={"search": query, "per_page": 50}, timeout=10)
            if resp.status_code == 200:
                results = []
                for item in resp.json():
                    title = item.get("title", "")
                    if isinstance(title, dict): title = title.get("rendered", "")
                    url = item.get("url", "")
                    if title and url:
                        results.append({"title": title, "url": fix_movie_url(url)})
                if results: return results
        except Exception as e:
            print(f"WP error: {e}")
    return []

# ================= FLASK ROUTES =================

@app.route('/')
def home():
    saved_html = ""
    for title, data in get_valid_saved().items():
        title_esc = html_lib.escape(title)
        title_q = quote(title, safe="")
        saved_html += f'''
        <div style="background:#222; padding:10px; margin:5px 0; border-radius:5px; display:flex; justify-content:space-between;">
            <span>{title_esc}</span>
            <a href="/remove/{title_q}" style="color:red; text-decoration:none;">Remove</a>
        </div>'''

    if not saved_html: saved_html = "<p style='color:#888;'>No saved movies yet.</p>"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1"><title>HDHub Scraper</title></head>
    <body style="font-family: Arial; background:#111; color:#fff; padding:20px; text-align:center;">
        <h1>🎬 HDHub4u Scraper</h1>
        <form action="/search" method="get">
            <input type="text" name="q" placeholder="Search movie..." required style="padding:10px; width:70%; max-width:300px; border-radius:5px; border:none;">
            <button type="submit" style="padding:10px 20px; background:#007bff; color:#fff; border:none; border-radius:5px;">Search</button>
        </form>

        <h3 style="margin-top:40px;">⭐ Saved Movies</h3>
        {saved_html}

        <br><br>
        <a href="/playlist.m3u" style="color:#28a745; font-weight:bold; font-size:18px; text-decoration:none;">📥 Download M3U Playlist</a>
    </body>
    </html>
    """

@app.route('/search')
def search():
    query = request.args.get("q", "").strip()
    if not query: return redirect("/")

    results = typesense_search(query)
    if not results: results = wp_search(query)

    results_html = ""
    for movie in results:
        title_esc = html_lib.escape(movie["title"])
        enc_url = base64.urlsafe_b64encode(movie["url"].encode()).decode()
        title_q = quote(movie["title"], safe="")

        results_html += f'''
        <div style="background:#222; padding:15px; margin:10px 0; border-radius:5px; display:flex; justify-content:space-between; align-items:center;">
            <span style="max-width:70%; font-size:14px;">{title_esc}</span>
            <form action="/save" method="post" style="margin:0;">
                <input type="hidden" name="title" value="{title_q}">
                <input type="hidden" name="url" value="{enc_url}">
                <button type="submit" style="padding:8px 15px; background:#28a745; color:#fff; border:none; border-radius:5px; cursor:pointer;">Save</button>
            </form>
        </div>'''

    if not results_html:
        results_html = "<p style='color:#aaa;'>No movies found. Try different spelling.</p>"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Search Results</title></head>
    <body style="font-family: Arial; background:#111; color:#fff; padding:20px;">
        <a href="/" style="color:#fff; text-decoration:none;">⬅ Back</a>
        <h3>Results for: "{html_lib.escape(query)}"</h3>
        {results_html}
    </body>
    </html>
    """

@app.route('/save', methods=['POST'])
def save():
    title = unquote(request.form.get("title", "")).strip()
    enc_url = request.form.get("url", "").strip()

    if title and enc_url:
        try:
            movie_url = base64.urlsafe_b64decode(enc_url.encode()).decode()
            # 🔥 Sirf 1 movie ka document likhte hain - baaki movies ko koi nuksan nahi
            fs_set(title, {"title": title, "url": movie_url, "saved_at": time.time()})
        except Exception as e:
            print(f"Save error: {e}")

    return redirect("/")

@app.route('/remove/<path:title>')
def remove(title):
    title = unquote(title)
    # 🔥 Sirf 1 movie delete. Empty collection bhi allowed hai (koi placeholder nahi chahiye)
    fs_delete(title)
    return redirect("/")

@app.route('/playlist.m3u')
def get_playlist():
    global cache_data

    if CACHE_TTL > 0 and cache_data["m3u"] and (time.time() - cache_data["timestamp"] < CACHE_TTL):
        saved_part = ""
        for title, data in get_valid_saved().items():
            enc_url = base64.urlsafe_b64encode(data["url"].encode()).decode()
            saved_part += f'#EXTINF:-1 group-title="⭐ Saved Movies",{title}\n'
            saved_part += f'https://{request.host}/play?url={enc_url}\n'
        return Response(cache_data["m3u"] + saved_part, mimetype='audio/x-mpegurl')

    categories = [("bollywood-movies", "Bollywood Movies"), ("south-hindi-movies", "South Hindi Movies")]

    m3u = "#EXTM3U\n"
    seen_urls = set()

    for cat_url, cat_name in categories:
        for page in range(1, 10):
            try:
                url = f"{BASE_URL}/category/{cat_url}/page/{page}/"
                resp = session.get(url, timeout=15)
                if resp.status_code != 200: continue
                soup = BeautifulSoup(resp.text, 'html.parser')

                for a_tag in soup.find_all('a', href=True):
                    title = a_tag.get_text(strip=True)
                    href = a_tag['href']
                    if not title or len(title) < 10: continue
                    if "(2026)" not in title and "(2025)" not in title: continue
                    if not href.startswith('http'): href = BASE_URL + href
                    if BASE_URL not in href: continue
                    if '/category/' in href or '/page/' in href or 'how-to-download' in href: continue

                    exclude = ["season", "ep-", "episode", "series", "s01", "s02", "how to download", "telegram", "play"]
                    if any(kw in title.lower() for kw in exclude): continue
                    if href in seen_urls: continue

                    seen_urls.add(href)
                    encoded_url = base64.urlsafe_b64encode(href.encode()).decode()
                    m3u += f'#EXTINF:-1 group-title="{cat_name}",{title}\n'
                    m3u += f'https://{request.host}/play?url={encoded_url}\n'
            except Exception as e:
                print(f"[!] Error fetching {cat_name} page {page}: {e}")

    for title, data in get_valid_saved().items():
        enc_url = base64.urlsafe_b64encode(data["url"].encode()).decode()
        m3u += f'#EXTINF:-1 group-title="⭐ Saved Movies",{title}\n'
        m3u += f'https://{request.host}/play?url={enc_url}\n'

    if CACHE_TTL > 0:
        cache_data["m3u"] = m3u
        cache_data["timestamp"] = time.time()

    return Response(m3u, mimetype='audio/x-mpegurl')

@app.route('/play')
def play_movie():
    encoded_url = request.args.get('url')
    if not encoded_url:
        return "No URL provided", 400

    encoded_url += "=" * ((4 - len(encoded_url) % 4) % 4)

    try:
        movie_url = base64.urlsafe_b64decode(encoded_url.encode()).decode()
    except Exception as e:
        return f"Invalid URL encoding: {str(e)}", 400

    try:
        movie_resp = session.get(movie_url, timeout=15)
        movie_soup = BeautifulSoup(movie_resp.text, 'html.parser')

        best_link = get_best_link(movie_soup, movie_url)
        if not best_link:
            return "No 1080p link found for this movie", 404

        print(f"[*] Best Link Found: {best_link}")

        hubcloud = None
        if "greenmotors" in best_link or "gadgetsweb" in best_link:
            hubcloud = extract_hubcloud_from_gadgets(best_link)
        elif "hubdrive.blog" in best_link:
            hubcloud = extract_hubcloud_from_hubdrive(best_link)
        else:
            hubcloud = best_link

        if hubcloud:
            if "hubdrive.blog" in hubcloud:
                print(f"[*] Intermediate Hubdrive found: {hubcloud}")
                hubcloud = extract_hubcloud_from_hubdrive(hubcloud)

            if hubcloud:
                final_link = process_hubcloud(hubcloud)
                if final_link:
                    return redirect(final_link, code=302)

        return "Failed to extract final HubCloud link. (Check Render Logs for details)", 500

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(error_details)
        return f"Error during extraction: {str(e)}\n{error_details}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, threaded=True)
