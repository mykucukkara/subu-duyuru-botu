#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SUBÜ Bilgisayar Mühendisliği duyuru/haber/etkinlik botu.

Yeni (Nuxt/headless CMS) siteden JSON API üzerinden duyuru, haber ve
etkinlikleri okur; başlangıç gününden sonra yayınlanmış ve daha önce
gönderilmemiş olanları Telegram kanalına link olarak yollar.

Durum "seen.json" dosyasında tutulur ve her çalıştırmada repoya commit edilir.

API (token gerektirmiyor):
  GET https://cmsservice.subu.edu.tr/posts/{announcement|news|event}/live?limit=N&unit=32208
Detay linki:
  https://bm.subu.edu.tr/node/{post_id}?unitID=32208
"""

import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

# Windows konsolu gibi UTF-8 olmayan ortamlarda print çökmesin.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# --- Ayarlar ---------------------------------------------------------------

SITE_URL = "https://bm.subu.edu.tr"
API_BASE = "https://cmsservice.subu.edu.tr"
UNIT_ID = "32208"          # Bilgisayar Mühendisliği bölümünün CMS birim kimliği
FETCH_LIMIT = 20           # her türden en fazla kaç öğe çekilsin
SOURCE_API = "cms-v2"      # seen.json şema sürümü (site değişince migrasyon için)

# API tür -> kanal etiketi ve simge
SOURCES = [
    {"type": "announcement", "name": "Duyuru",   "icon": "📢"},
    {"type": "news",         "name": "Haber",     "icon": "📰"},
    {"type": "event",        "name": "Etkinlik",  "icon": "📅"},
]

STATE_FILE = Path(__file__).parent / "seen.json"
REQUEST_TIMEOUT = 45
FETCH_RETRIES = 3
RETRY_WAIT = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SubuDuyuruBot/2.0)",
    "Accept": "application/json",
}

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# --- Durum (state) ---------------------------------------------------------

def load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            data.setdefault("start_date", None)
            data.setdefault("seen", [])
            data.setdefault("source_api", None)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"start_date": None, "seen": [], "source_api": None}


def save_state(state):
    state["seen"] = state["seen"][-1000:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --- Tarih ayrıştırma ------------------------------------------------------

def parse_date(text):
    """ISO tarih ('2026-11-05T08:08:12.000Z') -> date. Ayrıştırılamazsa None."""
    if not text:
        return None
    try:
        s = text.replace("Z", "+00:00")
        return datetime.fromisoformat(s).date()
    except (ValueError, AttributeError):
        return None


# --- API'den çekme ---------------------------------------------------------

def fetch_json(url):
    """JSON çek; zaman aşımı/geçici hatalarda birkaç kez yeniden dene."""
    last_err = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            last_err = e
            if attempt < FETCH_RETRIES:
                print(f"    (deneme {attempt}/{FETCH_RETRIES} başarısız: {e}; "
                      f"{RETRY_WAIT}sn sonra tekrar)")
                time.sleep(RETRY_WAIT)
    raise last_err


def extract_title(raw):
    t = raw.get("title")
    if isinstance(t, dict):
        return (t.get("tr") or next(iter(t.values()), "") or "").strip()
    return (t or "").strip()


def build_link(raw):
    """Öğenin dış linki varsa onu, yoksa site detay sayfasını döndür."""
    link = (raw.get("link") or "").strip()
    if link.startswith("http"):
        return link
    post_id = raw.get("post_id") or raw.get("id")
    return f"{SITE_URL}/node/{post_id}?unitID={UNIT_ID}"


def fetch_items(source):
    url = f"{API_BASE}/posts/{source['type']}/live?limit={FETCH_LIMIT}&unit={UNIT_ID}"
    data = fetch_json(url)
    if not isinstance(data, list):
        return []

    items = []
    for raw in data:
        post_id = raw.get("post_id") or raw.get("id")
        title = extract_title(raw)
        if not post_id or not title:
            continue
        items.append({
            "source": source["name"],
            "icon": source["icon"],
            "title": title,
            "url": build_link(raw),
            "key": f"{source['type']}:{post_id}",
            "date": parse_date(raw.get("date")),
        })
    return items


# --- Telegram --------------------------------------------------------------

def html_escape(text):
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


def send_telegram(item):
    date_str = item["date"].strftime("%d.%m.%Y") if item["date"] else ""
    title = html_escape(item["title"])
    msg = (
        f"{item['icon']} <b>{html_escape(item['source'])}</b>"
        + (f" · {date_str}" if date_str else "")
        + f"\n\n<a href=\"{item['url']}\">{title}</a>"
    )
    api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    r = requests.post(api, data=payload, timeout=REQUEST_TIMEOUT)
    if not r.ok:
        print(f"  ! Telegram hatası ({r.status_code}): {r.text}", file=sys.stderr)
    r.raise_for_status()


# --- Ana akış --------------------------------------------------------------

def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("HATA: TELEGRAM_TOKEN ve TELEGRAM_CHAT_ID ortam değişkenleri gerekli.",
              file=sys.stderr)
        sys.exit(1)

    state = load_state()
    today = date.today()

    # Tüm kaynakları çek
    all_items = []
    for source in SOURCES:
        try:
            found = fetch_items(source)
            print(f"{source['name']}: {len(found)} öğe bulundu.")
            all_items.extend(found)
        except (requests.RequestException, ValueError) as e:
            print(f"  ! {source['name']} alınamadı: {e}", file=sys.stderr)

    # --- Migrasyon / ilk çalıştırma ---
    # Site/API değiştiyse (ya da hiç çalışmadıysa) geçmişi TOPLUCA GÖNDERME:
    # mevcut tüm öğeleri 'görüldü' say, başlangıç tarihini bugüne sabitle.
    if state["source_api"] != SOURCE_API or state["start_date"] is None:
        state["seen"] = sorted({it["key"] for it in all_items})
        state["start_date"] = today.isoformat()
        state["source_api"] = SOURCE_API
        save_state(state)
        print(f"Kurulum/migrasyon tamamlandı (API={SOURCE_API}). "
              f"Başlangıç tarihi: {today.isoformat()}. "
              f"{len(state['seen'])} mevcut öğe 'görüldü' işaretlendi, hiçbiri gönderilmedi.")
        return

    start_date = date.fromisoformat(state["start_date"])
    seen = set(state["seen"])

    to_send = []
    for item in all_items:
        if item["key"] in seen:
            continue
        if item["date"] is None or item["date"] < start_date:
            seen.add(item["key"])  # eski/tarihsiz: gönderme ama görüldü say
            continue
        to_send.append(item)

    to_send.sort(key=lambda x: x["date"])  # eskiden yeniye (kronolojik)

    if not to_send:
        print("Yeni duyuru yok.")
    else:
        print(f"{len(to_send)} yeni öğe gönderiliyor...")
        for item in to_send:
            try:
                send_telegram(item)
                seen.add(item["key"])
                print(f"  ✓ [{item['source']}] {item['title']}")
                time.sleep(1)
            except requests.RequestException:
                print(f"  ✗ Gönderilemedi: {item['title']}", file=sys.stderr)

    state["seen"] = list(seen)
    save_state(state)
    print("Bitti.")


if __name__ == "__main__":
    main()
