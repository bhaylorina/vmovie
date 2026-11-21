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

app = Flask(__name__)
JSONBIN_ID = "6b0131faac6210605a99192c"
JSONBIN_KEY = "$2a$10$NXJcYdSiU7drll/yRzSEK.rnmvMBGAwWfLstiSisvpDfNijjjRGfu"

BASE_URL = "https://new15.hdhub4u.cl"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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

# Simple In-Memory Cache
cache_data = {"m3u": None, "timestamp": 0}
saved_movies = {}
def load_saved_movies_from_cloud():
    global saved_movies
    try:
        headers = {"X-Master-Key": JSONBIN_KEY}
        resp = std_requests.get(f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}/latest", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("record", {})
            if isinstance(data, dict) and data:
                saved_movies.update(data)
                print("[+] Cloud se saved movies load ho gayi!")
    except Exception as e:
        print(f"[-] Cloud load error: {e}")

def sync_saved_movies_to_cloud():
    try:
        headers = {
            "X-Master-Key": JSONBIN_KEY,
            "Content-Type": "application/json"
        }
        std_requests.put(f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}", json=saved_movies, headers=headers, timeout=10)
        print("[+] Saved movies Cloud me sync ho gayi!")
    except Exception as e:
        print(f"[-] Cloud sync error: {e}")
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
                        
                        # Pehle Hubcloud dhundho
                        if 'hubcloud' in text or 'hubcloud' in href:
                            return a['href']
                        # Agar nahi mila toh Hubdrive save karo
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

# 🛑 गेमड्राइव बायपास लॉजिक
def convert_pixeldrain_to_direct(url):
    if not url:
        return None
        
    url = url.replace('&amp;', '&')
    
    # GameDrive Bypass Regex
    match = re.search(r'https?://(?:pixeldra\.in|pixeldrain\.com|pixeldrain\.net|pixeldrain\.dev)/(?:u|api/file|l)/([^?\s]+)', url)
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
        
        all_r2_links = re.findall(r'https?://[a-zA-Z0-9._-]+\.r2\.cloudflarestorage\.com/[^\s"\'<>]+', html_text)
        valid_r2_links = [l for l in all_r2_links if 't3apac' not in l.lower() and 'fslv2' not in l.lower()]
        
        if valid_r2_links:
            print("--> SUCCESS: R2 Link Found!")
            for link in valid_r2_links:
                if 'X-Amz-Expires=28800' in link:
                    return link
            return valid_r2_links[0]

        # 🔥 PixelServer Fallback (Indentation FIXED HERE) 🔥
        found_links = set()
        for match in re.finditer(r'pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9]+)', html_text):
            found_links.add(match.group(1))
        for a in gen_soup.find_all('a'):
            for attr in ['data-url', 'data-link', 'data-href', 'data-src']:
                val = a.get(attr)
                if val:
                    for m in re.finditer(r'pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9]+)', val):
                        found_links.add(m.group(1))
        for match in re.finditer(r'[a-zA-Z0-9+/]{20,}={0,2}', html_text):
            b64_str = match.group(0)
            try:
                decoded = base64.b64decode(b64_str + "=" * ((4 - len(b64_str) % 4) % 4)).decode('utf-8')
                for m in re.finditer(r'pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9]+)', decoded):
                    found_links.add(m.group(1))
            except: pass
        for match in re.finditer(r"atob\(['\"]([^'\"]+)['\"]\)", html_text):
            b64_str = match.group(1)
            try:
                decoded = base64.b64decode(b64_str + "=" * ((4 - len(b64_str) % 4) % 4)).decode('utf-8')
                for m in re.finditer(r'pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9]+)', decoded):
                    found_links.add(m.group(1))
            except: pass
            
        parsed_url = urllib.parse.urlparse(gen_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        for key, values in query_params.items():
            for val in values:
                try:
                    decoded = base64.b64decode(val + "=" * ((4 - len(val) % 4) % 4)).decode('utf-8')
                    for m in re.finditer(r'pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9]+)', decoded):
                        found_links.add(m.group(1))
                except: pass
                for m in re.finditer(r'pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9]+)', val):
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
    global saved_movies
    now = time.time()
    valid = {}
    
    # 🔥 Cloud se data fetch karo agar memory khali hai 🔥
    if not saved_movies:
        load_saved_movies_from_cloud()

    for title, data in list(saved_movies.items()):
        # Check karo ki data ek dictionary hai ya nahi (init: true ko ignore karne ke liye)
        if isinstance(data, dict):
            if now - data.get("saved_at", 0) <= SAVED_DURATION:
                valid[title] = data
            else:
                del saved_movies[title]
        else:
            # Agar koi invalid data hai (jaise init: true), toh usko memory se delete kar do
            del saved_movies[title]
            
    # Agar kuch invalid ya expire movies delete hui hain, toh cloud ko update kar do
    if len(valid) != len(saved_movies):
        sync_saved_movies_to_cloud()
        
    return valid
        
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
            saved_movies[title] = {"title": title, "url": movie_url, "saved_at": time.time()}
            
            # 🔥 Cloud me save karo 🔥
            sync_saved_movies_to_cloud() 
            
        except Exception as e:
            print(f"Save error: {e}")
            
    return redirect("/")

@app.route('/remove/<path:title>')
def remove(title):
    title = unquote(title)
    saved_movies.pop(title, None)
    
    # 🔥 Cloud se bhi delete karo 🔥
    sync_saved_movies_to_cloud()
    
    return redirect("/")

@app.route('/playlist.m3u')
def get_playlist():
    global cache_data
    if cache_data["m3u"] and (time.time() - cache_data["timestamp"] < 0):
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
    
    cache_data["m3u"] = m3u
    cache_data["timestamp"] = time.time()
    
    return Response(m3u, mimetype='audio/x-mpegurl')

@app.route('/play')
def play_movie():
    encoded_url = request.args.get('url')
    if not encoded_url:
        return "No URL provided", 400

    # 🔥 FIX: Missing Base64 Padding ko wapas add karein 🔥
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
            # Agar hblinks se hubdrive link aaya hai, toh usko convert karein
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
