from urllib.parse import urlparse
from bs4 import BeautifulSoup

# RSS'de görseli maksimum kapsayıcılık ile bulmaya çalışır
def extract_image(entry, fallback_domain: str = None):
    # 1) media:content / media:thumbnail
    for key in ('media_content', 'media_thumbnail'):
        val = getattr(entry, key, None)
        if val:
            if isinstance(val, list) and val:
                url = val[0].get('url') or val[0].get('href')
                if url:
                    return url
            elif isinstance(val, dict):
                url = val.get('url') or val.get('href')
                if url:
                    return url
    # 2) enclosures
    encl = getattr(entry, 'enclosures', None)
    if encl:
        for e in encl:
            href = e.get('href') or e.get('url')
            if href and any(href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                return href
    # 3) content/summary içindeki <img>
    for field in ('content', 'summary', 'description'):
        val = getattr(entry, field, None)
        if isinstance(val, list) and val:
            html = val[0].get('value')
        else:
            html = val
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            img = soup.find('img')
            if img and img.get('src'):
                return img['src']
    # 4) favicon (son çare)
    domain = fallback_domain or (urlparse(getattr(entry, 'link', '')).netloc)
    if domain:
        return f'https://icons.duckduckgo.com/ip3/{domain}.ico'
    return None
