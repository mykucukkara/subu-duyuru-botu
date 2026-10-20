#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SUBÜ Bilgisayar Mühendisliği duyuru/etkinlik/haber botu.

Üç sayfayı tarar, yeni (bugünden itibaren yayınlanmış) ve daha önce
gönderilmemiş öğeleri Telegram kanalına link olarak yollar.

Durum "seen.json" dosyasında tutulur ve her çalıştırmada repoya commit edilir.
"""

import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Windows konsolu gibi UTF-8 olmayan ortamlarda print çökmesin.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# --- Ayarlar ---------------------------------------------------------------

BASE_URL = "https://bm.subu.edu.tr"

SOURCES = [
    {"name": "Duyuru",   "url": "https://bm.subu.edu.tr/tr/duyurular"},
    {"name": "Etkinlik", "url": "https://bm.subu.edu.tr/tr/etkinlikler"},
    {"name": "Haber",    "url": "https://bm.subu.edu.tr/tr/haberler"},
]

STATE_FILE = Path(__file__).parent / "seen.json"
REQUEST_TIMEOUT = 45          # saniye (site bazen yavaş yanıt veriyor)
FETCH_RETRIES = 3             # zaman aşımı/geçici hatada kaç kez denensin
RETRY_WAIT = 5               # denemeler arası bekleme (saniye)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SubuDuyuruBot/1.0)"}

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


# --- Durum (state) ---------------------------------------------------------

def load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            data.setdefault("start_date", None)
            data.setdefault("seen", [])
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"start_date": None, "seen": []}


def save_state(state):
    # "seen" listesini sınırlı tut (çok büyümesin)
    state["seen"] = state["seen"][-500:]
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --- Tarih ayrıştırma ------------------------------------------------------

def parse_date(text):
    """'15 / 10 / 2026' -> date(2026, 10, 15). Ayrıştırılamazsa None."""
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", text)
    if not m:
        return None
    day, month, year = (int(m.group(i)) for i in (1, 2, 3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


# --- İçerik anahtarı (tekilleştirme için) ----------------------------------

def item_key(url):
    """
    /tr/node/1202 ve /index.php/tr/node/1202 aynı içerik -> aynı anahtar.
    """
    m = re.search(r"/node/(\d+)", url)
    if m:
        return f"node:{m.group(1)}"
    m = re.search(r"/etkinlik/([^/?#]+)", url)
    if m:
        return f"etkinlik:{m.group(1)}"
    return url


# --- Sayfa tarama ----------------------------------------------------------

def fetch_html(url):
    """Sayfayı indir; zaman aşımı/geçici hatalarda birkaç kez yeniden dene."""
    last_err = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as e:
            last_err = e
            if attempt < FETCH_RETRIES:
                print(f"    (deneme {attempt}/{FETCH_RETRIES} başarısız: {e}; "
                      f"{RETRY_WAIT}sn sonra tekrar)")
                time.sleep(RETRY_WAIT)
    raise last_err


def fetch_items(source):
    html = fetch_html(source["url"])
    soup = BeautifulSoup(html, "html.parser")

    items = []
    for li in soup.select("ul.list-duyuru-etkinlik > li"):
        a = li.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a["href"]
        url = urljoin(BASE_URL, href)

        date_span = li.find("span", class_="content-list-view-date")
        published = parse_date(date_span.get_text()) if date_span else None

        if not title or not url:
            continue

        items.append({
            "source": source["name"],
            "title": title,
            "url": url,
            "key": item_key(url),
            "date": published,
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
        f"📢 <b>{html_escape(item['source'])}</b>"
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

    # İlk çalıştırma: başlangıç tarihini bugüne sabitle.
    # Bu tarihten ÖNCE yayınlanmış geçmiş duyurular hiç gönderilmez.
    first_run = state["start_date"] is None
    if first_run:
        state["start_date"] = today.isoformat()
        print(f"İlk çalıştırma. Başlangıç tarihi: {today.isoformat()} "
              f"(bu tarihten eski duyurular gönderilmeyecek).")
    start_date = date.fromisoformat(state["start_date"])

    seen = set(state["seen"])
    all_items = []
    for source in SOURCES:
        try:
            found = fetch_items(source)
            print(f"{source['name']}: {len(found)} öğe bulundu.")
            all_items.extend(found)
        except requests.RequestException as e:
            print(f"  ! {source['name']} alınamadı: {e}", file=sys.stderr)

    # Gönderilecekler: başlangıç tarihinden sonra yayınlanmış + daha önce görülmemiş.
    # Tarihe göre eskiden yeniye sırala ki kanala kronolojik düşsün.
    to_send = []
    for item in all_items:
        if item["key"] in seen:
            continue
        if item["date"] is None or item["date"] < start_date:
            # Tarihsiz ya da başlangıçtan eski: gönderme, ama görüldü say.
            seen.add(item["key"])
            continue
        to_send.append(item)

    to_send.sort(key=lambda x: x["date"])

    if not to_send:
        print("Yeni duyuru yok.")
    else:
        print(f"{len(to_send)} yeni duyuru gönderiliyor...")
        for item in to_send:
            try:
                send_telegram(item)
                seen.add(item["key"])
                print(f"  ✓ [{item['source']}] {item['title']}")
                time.sleep(1)  # Telegram hız sınırına takılmamak için
            except requests.RequestException:
                # Gönderilemeyeni 'görüldü' sayma; sonraki turda tekrar denenir.
                print(f"  ✗ Gönderilemedi: {item['title']}", file=sys.stderr)

    state["seen"] = sorted(seen) if False else list(seen)
    save_state(state)
    print("Bitti.")


if __name__ == "__main__":
    main()
