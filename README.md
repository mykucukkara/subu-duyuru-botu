# SUBÜ Bilgisayar Mühendisliği Duyuru Botu

[bm.subu.edu.tr](https://bm.subu.edu.tr) sitesindeki **duyuru, etkinlik ve haber**
sayfalarını tarar; yeni çıkan öğeleri Telegram kanalına **link olarak** gönderir.

- ⏰ Hafta içi/hafta sonu her gün, **TR saati 08:00–17:00 arası saat başı** çalışır.
- 🔁 Aynı duyuruyu iki kez göndermez (`seen.json` ile takip).
- 🆕 Yeni duyuru yoksa hiçbir şey göndermez.
- 📅 İlk çalıştığı günden **önceki geçmiş duyuruları göndermez** (tek seferde geçmişi boşaltmaz).
- ☁️ GitHub Actions üzerinde çalışır — **sunucu kiralamaya gerek yok**, private repoda ücretsiz.

---

## Kurulum

### 1) Telegram botu oluştur ve token al

1. Telegram'da **[@BotFather](https://t.me/BotFather)**'a yaz.
2. `/newbot` komutunu gönder, bir isim ve kullanıcı adı ver.
3. BotFather sana şöyle bir **token** verir:
   `123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   Bunu not al (bu `TELEGRAM_TOKEN`).

### 2) Botu kanalına ekle

1. Kanalının **Ayarlar → Yöneticiler → Yönetici Ekle** bölümünden botunu ekle.
2. Bota en azından **"Mesaj Gönderme"** yetkisi ver.

### 3) Kanalın chat ID'sini bul (`TELEGRAM_CHAT_ID`)

- **Herkese açık kanal** ise: `@kanalkullaniciadi` yazman yeterli.
- **Özel kanal** ise sayısal ID lazım (`-100...` ile başlar):
  1. Kanala herhangi bir mesaj at.
  2. Tarayıcıda şu adresi aç (token'ını koy):
     `https://api.telegram.org/bot<TOKEN>/getUpdates`
  3. Dönen JSON içinde `"chat":{"id":-1001234567890, ...}` değerini bul. `TELEGRAM_CHAT_ID` budur.

### 4) Bu projeyi GitHub'a (private repo) yükle

```bash
git init
git add .
git commit -m "ilk sürüm: duyuru botu"
git branch -M main
git remote add origin https://github.com/<kullanici>/<repo>.git
git push -u origin main
```

> Repoyu oluştururken **Private** seç. GitHub Actions private repolarda da ücretsiz
> (aylık dakika kotası dahilinde; bu bot çok az dakika harcar).

### 5) Secret'ları ekle

GitHub'da repo sayfasında:
**Settings → Secrets and variables → Actions → New repository secret**

İki secret ekle:

| İsim               | Değer                              |
|--------------------|------------------------------------|
| `TELEGRAM_TOKEN`   | BotFather'dan aldığın token        |
| `TELEGRAM_CHAT_ID` | `@kanaladi` veya `-100...` ID       |

### 6) Workflow iznini kontrol et

`seen.json` dosyasını repoya geri yazabilmesi için:
**Settings → Actions → General → Workflow permissions →
"Read and write permissions"** seçili olmalı.
(Zaten `.github/workflows/duyuru-bot.yml` içinde `permissions: contents: write` tanımlı.)

### 7) Test et

**Actions** sekmesi → **SUBÜ Duyuru Botu** → **Run workflow** (manuel tetikleme).
İlk çalıştırmada geçmiş duyurular gönderilmez; sadece `start_date` bugüne sabitlenir ve
`seen.json` commit'lenir. Bundan sonra çıkan yeni duyurular kanala düşer.

---

## Çalışma mantığı

- `bot.py` üç sayfayı tarar, her öğenin başlık/link/tarihini çıkarır.
- Bir öğe gönderilir eğer: tarihi **başlangıç gününden sonra** VE daha önce gönderilmemiş.
- Gönderilenler `seen.json`'a yazılır ve GitHub Actions bunu repoya commit eder.

## Saat ayarını değiştirmek

`.github/workflows/duyuru-bot.yml` içindeki cron satırı **UTC**'dir. Türkiye UTC+3'tür
(yaz saati uygulaması yok, sabit). Örnek: TR 08–17 → UTC 05–14 → `0 5-14 * * *`.
Sadece hafta içi istersen sonuna gün aralığı ekle: `0 5-14 * * 1-5`.

## Yerelde çalıştırma (opsiyonel)

```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN="..."      # Windows PowerShell: $env:TELEGRAM_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python bot.py
```

## Notlar

- GitHub Actions cron'u yoğunlukta birkaç dakika gecikmeli tetikleyebilir; saat başı mantığı için sorun olmaz.
- Site HTML yapısı değişirse `bot.py` içindeki `ul.list-duyuru-etkinlik` seçicisi güncellenmelidir.
