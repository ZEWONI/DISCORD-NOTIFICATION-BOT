# Notification Bot

Çeşitli platformlardan (YouTube, Kick, RSS) gelen bildirimleri anında Discord sunucunuza gönderen çok amaçlı bir bildirim botu.

## ✨ Özellikler

- **Kick Bildirimleri:** Takip edilen kanallar yayın açtığında anında bildirim gönderir.
- **YouTube Bildirimleri:** Takip edilen YouTube kanallarına yeni video yüklendiğinde bildirim gönderir.
- **RSS/Feed Bildirimleri:** Herhangi bir web sitesinin RSS/Atom feed'ini takip ederek yeni yazıları bildirir.
- **Slash Komutları:** Modern ve kullanımı kolay slash komutları ile yönetilir.
- **Görsel Destek:** RSS ve YouTube bildirimlerinde içeriğe ait görselleri mesaja ekler.
- **Kalıcı Hafıza:** `subscriptions.json` dosyası sayesinde bot yeniden başlasa bile abonelikleri unutmaz.

## ⚙️ Komutlar

- `/help`: Botun tüm komutlarını ve açıklamalarını gösterir.
- `/kick_ekle <kullanici_adi> <kanal>`: Bir Kick yayıncısını takip listesine ekler.
- `/youtube_ekle <channel_id> <kanal>`: Bir YouTube kanalını takip listesine ekler.
- `/feed_ekle <feed_url> <kanal>`: Bir web sitesi RSS feed'ini takip listesine ekler.
- `/abonelikleri_listele`: Mevcut tüm abonelikleri listeler.
- `/abonelik_sil <numara>`: Belirtilen numaradaki aboneliği siler.

## 🚀 Kurulum

1.  **Projeyi Klonlayın:**
    ```bash
    git clone https://github.com/ZEWONI/DISCORD-NOTIFICATION-BOT.git
    cd DISCORD-NOTIFICATION-BOT
    ```

2.  **`.env` Dosyasını Oluşturun:**
    Proje ana dizininde `.env` adında bir dosya oluşturun ve içine Discord bot token'ınızı girin:
    ```
    DISCORD_TOKEN=BURAYA_DISCORD_BOT_TOKENINIZI_YAPISTIRIN
    ```

3.  **Python Sanal Ortamını Kurun:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

4.  **Gerekli Kütüphaneleri Yükleyin:**
    ```bash
    pip install discord.py python-dotenv feedparser aiohttp
    ```

5.  **Botu Çalıştırın:**
    ```bash
    python3 bot.py
    ```
