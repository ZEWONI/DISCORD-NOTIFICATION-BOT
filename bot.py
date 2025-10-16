import discord
from discord.ext import tasks
import os
import json
import feedparser
import aiohttp
from dotenv import load_dotenv
from datetime import datetime
import re
import time
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# .env dosyasındaki değişkenleri yükle
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUBS_FILE = 'subscriptions.json'
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

# --- Veri Saklama Fonksiyonları ---
def load_subscriptions():
    if not os.path.exists(SUBS_FILE): return []
    try:
        with open(SUBS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return []

def save_subscriptions(subscriptions):
    with open(SUBS_FILE, 'w', encoding='utf-8') as f: json.dump(subscriptions, f, indent=4)

# YENİ: Bu fonksiyon artık çalışan bir tarayıcıyı parametre olarak alıyor
def get_kick_channel_data_with_driver(driver, username):
    data = None
    try:
        api_url = f"https://kick.com/api/v2/channels/{username}"
        driver.get(api_url)
        # Sayfadaki <pre> etiketinin yüklenmesini 10 saniyeye kadar bekle
        wait = WebDriverWait(driver, 10)
        pre_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'pre')))
        json_text = pre_element.text
        data = json.loads(json_text)
    except Exception as e:
        print(f"Selenium ile Kick verisi alınırken hata ({username}): {e}")
    return data

@bot.event
async def on_ready():
    print(f'{bot.user} olarak giriş yapıldı.')
    # GECKODRIVER'I BOT BAŞLARKEN BİR KERE İNDİRİYORUZ
    try:
        print("GeckoDriver kontrol ediliyor/indiriliyor...")
        GeckoDriverManager().install()
        print("GeckoDriver hazır.")
    except Exception as e:
        print(f"GeckoDriver indirilirken hata oluştu: {e}")
    await tree.sync()
    check_feeds.start()
    print("Slash komutları senkronize edildi ve feed kontrol döngüsü başladı.")

# --- Slash Komutları (Değişiklik yok) ---
# ... (Tüm slash komutları aynı kalıyor, buraya tekrar eklemiyorum)

# --- ARKA PLAN GÖREVİ (FEED KONTROLÜ) - MİMARİ DEĞİŞTİ ---
@tasks.loop(minutes=5)
async def check_feeds():
    await bot.wait_until_ready()
    subscriptions = load_subscriptions()
    if not subscriptions: return
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Tüm abonelikler kontrol ediliyor...")

    kick_subs = [s for s in subscriptions if s['type'] == 'kick']
    feed_subs = [s for s in subscriptions if s['type'] in ['youtube', 'rss']]
    
    # --- KICK KONTROL MANTIĞI (YENİ MİMARİ) ---
    if kick_subs:
        driver = None
        try:
            options = FirefoxOptions()
            options.add_argument("--headless")
            options.binary_location = '/usr/lib/firefox-esr/firefox-esr'
            # GeckoDriver'ı her seferinde indirmek yerine kurulu olanı kullanıyoruz
            driver = webdriver.Firefox(service=FirefoxService(), options=options)
            
            for sub in kick_subs:
                username = sub['username']
                # Botu dondurmamak için senkron çalışan fonksiyonu ayrı bir iş parçacığında çalıştır
                data = await bot.loop.run_in_executor(None, get_kick_channel_data_with_driver, driver, username)
                
                if data is None: continue

                livestream_data = data.get('livestream')
                is_live_now = livestream_data is not None
                was_live_before = sub.get('was_live', False)
                if is_live_now and not was_live_before:
                    channel = bot.get_channel(sub['discord_channel_id'])
                    if channel:
                        embed = discord.Embed(title=f"🔴 {data['user']['username']} şimdi yayında!", url=f"https://kick.com/{data['user']['username']}", description=f"**{livestream_data['session_title']}**", color=0x00ff00)
                        embed.set_author(name="Kick.com"); embed.set_thumbnail(url=data['user']['profile_pic'])
                        if livestream_data.get('thumbnail'): embed.set_image(url=livestream_data['thumbnail']['url'])
                        embed.add_field(name="Kategori", value=livestream_data['categories'][0]['name'], inline=True)
                        embed.add_field(name="İzleyici", value=livestream_data.get('viewer_count', 0), inline=True)
                        embed.set_footer(text="Yayın başladı!")
                        await channel.send(f"Hey @everyone! `{data['user']['username']}` Kick'te yayın başlattı!", embed=embed)
                        print(f"Kick bildirimi gönderildi: {data['user']['username']}")
                    sub['was_live'] = True
                    save_subscriptions(subscriptions)
                elif not is_live_now and was_live_before:
                    sub['was_live'] = False
                    save_subscriptions(subscriptions)
                    print(f"Kick yayını sona erdi: {username}")
        except Exception as e:
            print(f"Selenium tarayıcı başlatılırken veya çalışırken genel bir hata oluştu: {e}")
        finally:
            if driver:
                driver.quit()
                print("Selenium tarayıcısı kapatıldı.")

    # --- RSS / YOUTUBE KONTROL MANTIĞI ---
    async with aiohttp.ClientSession() as session:
        for sub in feed_subs:
            try:
                async with session.get(sub.get('url')) as response:
                    if response.status != 200: continue
                    content = await response.text()
                    feed = feedparser.parse(content)
                    if not feed.entries: continue
                    latest_entry = feed.entries[0]
                    entry_id = latest_entry.get('id') or latest_entry.get('link')
                    if entry_id is None: continue
                    if sub.get('last_entry_id') is None:
                        sub['last_entry_id'] = entry_id
                        save_subscriptions(subscriptions); continue
                    if sub.get('last_entry_id') != entry_id:
                        channel = bot.get_channel(sub['discord_channel_id'])
                        if channel:
                            embed = discord.Embed(title=f"🆕 Yeni İçerik: {latest_entry.title}", url=latest_entry.link, description=f"**{feed.feed.title}** sitesinden yeni içerik var!", color=discord.Color.red() if sub['type'] == 'youtube' else discord.Color.green())
                            if 'author' in latest_entry: embed.set_author(name=latest_entry.author)
                            image_url = None
                            if 'media_thumbnail' in latest_entry and latest_entry.media_thumbnail: image_url = latest_entry.media_thumbnail[0].get('url')
                            elif 'summary' in latest_entry: match = re.search(r'<img[^>]+src="([^">]+)"', latest_entry.summary); image_url = match.group(1) if match else None
                            if image_url: embed.set_image(url=image_url)
                            await channel.send(embed=embed)
                        sub['last_entry_id'] = entry_id
                        save_subscriptions(subscriptions)
            except Exception as e:
                print(f"Bir abonelik işlenirken hata oluştu ({sub.get('id')}): {e}")

bot.run(TOKEN)