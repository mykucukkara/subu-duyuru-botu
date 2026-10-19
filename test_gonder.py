#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tek seferlik test: sitedeki en güncel duyuruyu kanala gönderir.
seen.json'a dokunmaz, normal botu etkilemez."""

import bot

items = []
for source in bot.SOURCES:
    try:
        items.extend(bot.fetch_items(source))
    except Exception as e:  # noqa: BLE001
        print(f"{source['name']} alınamadı: {e}")

items = [i for i in items if i["date"]]
if not items:
    raise SystemExit("Hiç duyuru bulunamadı.")

latest = max(items, key=lambda x: x["date"])
print(f"Gönderiliyor: [{latest['source']}] {latest['title']} ({latest['date']})")
bot.send_telegram(latest)
print("✓ Gönderildi.")
