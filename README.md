# Samsun Haber – Görselli RSS İndeksi

Samsun odaklı kaynaklardan RSS çeken, **kart tabanlı**, **görselli**, **hızlı aramalı** web arayüz.

## Başlat
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Tarayıcıda: http://localhost:8000

## Docker
```bash
docker build -t samsun-rss .
docker run -p 8000:8000 samsun-rss
```

## Özellikler
- Çoklu kaynaktan çekim ve **tek listede birleşik görünüm**
- **Görseller** (media:content, thumbnail, enclosure, içerikten img, yoksa favicon)
- **Arama** (başlık + özet), **kaynağa göre filtre**
- **Sonsuz kaydırma** (infinite scroll) için JSON API (`/api/articles`)
- **3 dakikada bir otomatik güncelleme** (background thread)
- Yinelenen bağlantıları **normalize ederek** tekilleştirme
