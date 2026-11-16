#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Yerel ve uzak (remote) seen.json'u birleştirir.

Eşzamanlı GitHub Actions çalışmaları aynı anda seen.json'u değiştirip
push edince çakışma olur. Bu betik iki dosyadaki 'seen' listelerinin
BİRLEŞİMİNİ alır (hiçbir gönderilmiş öğe kaybolmaz, tekrar gönderilmez),
start_date / source_api için yerel değeri korur ve sonucu yerel dosyaya yazar.

Kullanım: python merge_seen.py <yerel_seen.json> <remote_seen.json>
"""

import json
import re
import sys

MAX_KEEP = 2000  # dosya şişmesin diye tutulacak en fazla kayıt


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def numeric_id(key):
    # "announcement:23723" -> 23723 (sıralama için; yoksa 0)
    m = re.search(r"(\d+)\s*$", key)
    return int(m.group(1)) if m else 0


def main():
    local_path, remote_path = sys.argv[1], sys.argv[2]
    local = load(local_path)
    remote = load(remote_path)

    seen = set(local.get("seen", [])) | set(remote.get("seen", []))
    # En yeni (yüksek id'li) kayıtları tut
    kept = sorted(seen, key=numeric_id, reverse=True)[:MAX_KEEP]

    merged = dict(local)  # start_date, source_api yerelden korunur
    merged["seen"] = kept

    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Birleştirildi: yerel={len(local.get('seen', []))} "
          f"remote={len(remote.get('seen', []))} -> {len(kept)} kayıt")


if __name__ == "__main__":
    main()
