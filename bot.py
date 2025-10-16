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

# .env dosyasındaki değişkenleri yükle
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUBS_FILE = 'subscriptions.json'
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

# --- Veri Saklama Fonksiyonları --- (Aynı kalıyor)
def load_subscriptions():
    if not os.path.exists(SUBS_FILE): return []
    try:
        with open(SUBS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return []

def save_subscriptions(subscriptions):
    with open(SUBS_FILE, 'w', encoding='utf-8') as f: json.dump(subscriptions, f, indent=4)

# YENİ: Selenium Tarayıcı Fonksiyonu
def get_kick_channel_data(username):
    # Görünmez (headless) mod için tarayıcı seçeneklerini ayarla
    options = FirefoxOptions()
    options.add_argument("--headless")
    
    # Tarayıcıyı başlat
    driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)
    
    data = None
    try:
        # API adresine git
        api_url = f"https://kick.com/api/v2/channels/{username}"
        driver.get(api_url)
        # Sayfanın yüklenmesi için kısa bir bekleme
        time.sleep(3)
        # Sayfadaki veriyi çek (API doğrudan JSON döndürdüğü için body içindeki pre etiketini alırız)
        json_text = driver.find_element(By.TAG_NAME, 'pre').text
        data = json.loads(json_text)
    except Exception as e:
        print(f"Selenium ile Kick verisi alınırken hata: {e}")
    finally:
        # Hata olsa da olmasa da tarayıcıyı mutlaka kapat
        driver.quit()
        
    return data

# --- BOT HAZIR OLDUĞUNDA ÇALIŞACAK KOD --- (Aynı kalıyor)
@bot.event
async def on_ready():
    print(f'{bot.user} olarak giriş yapıldı.')
    await tree.sync()
    check_feeds.start()
    print("Slash komutları senkronize edildi ve feed kontrol döngüsü başladı.")

# --- SLASH KOMUTLARI --- (Hepsi aynı kalıyor)
@tree.command(name="help", description="Bot komutları hakkında bilgi verir.")
# ... (kod aynı)
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Yardım Menüsü - NOTIFICATION BOT", description="Bu bot YouTube, Kick ve web sitelerinden yeni içerikleri takip eder.", color=discord.Color.blue())
    embed.add_field(name="/kick_ekle", value="Bir Kick kanalını takip etmek için kullanılır.\n`kullanici_adi`: Kick yayıncısının kullanıcı adı.\n`kanal`: Bildirimlerin gönderileceği Discord kanalı.", inline=False)
    embed.add_field(name="/youtube_ekle", value="Bir YouTube kanalını takip etmek için kullanılır.\n`channel_id`: YouTube kanalının 'UC...' ile başlayan ID'si.", inline=False)
    embed.add_field(name="/feed_ekle", value="Bir web sitesinin RSS/Atom feed'ini takip etmek için kullanılır.\n`feed_url`: Sitenin RSS adresi.", inline=False)
    embed.add_field(name="/abonelikleri_listele", value="Tüm aktif abonelikleri listeler.", inline=False)
    embed.add_field(name="/abonelik_sil", value="Listeden bir aboneliği numarasını girerek siler.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="kick_ekle", description="Yayın açıldığında bildirim almak için bir Kick kanalını takip et.")
# ... (kod aynı)
async def kick_ekle(interaction: discord.Interaction, kullanici_adi: str, kanal: discord.TextChannel):
    kullanici_adi = kullanici_adi.lower()
    subscriptions = load_subscriptions()
    for sub in subscriptions:
        if sub.get('type') == 'kick' and sub.get('username') == kullanici_adi and sub['discord_channel_id'] == kanal.id:
            await interaction.response.send_message(f"`{kullanici_adi}` adlı Kick kanalı zaten <#{kanal.id}> kanalında takip ediliyor.", ephemeral=True); return
    new_sub = {'type': 'kick', 'id': f"kick_{kullanici_adi}", 'username': kullanici_adi, 'discord_channel_id': kanal.id, 'was_live': False}
    subscriptions.append(new_sub); save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ Başarılı! Kick kanalı (`{kullanici_adi}`) yayın açtığında artık <#{kanal.id}> kanalına bildirilecek.")

# ... (Diğer komutlar youtube_ekle, feed_ekle, listele, sil aynı)

# --- ARKA PLAN GÖREVİ (FEED KONTROLÜ) --- (ANA DEĞİŞİKLİK BURADA)
@tasks.loop(minutes=5) # Selenium daha yavaş olduğu için süreyi 5 dakikaya çıkarmak iyi olabilir
async def check_feeds():
    await bot.wait_until_ready()
    subscriptions = load_subscriptions()
    if not subscriptions: return
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Tüm abonelikler kontrol ediliyor...")

    async with aiohttp.ClientSession() as session:
        for sub in subscriptions:
            try:
                if sub['type'] == 'kick':
                    username = sub['username']
                    # Botu dondurmamak için senkron çalışan Selenium fonksiyonunu ayrı bir iş parçacığında çalıştır
                    data = await bot.loop.run_in_executor(None, get_kick_channel_data, username)
                    
                    if data is None:
                        print(f"Kick verisi alınamadı ({username}).")
                        continue
                    
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
                    
                    elif not is_live_now and was_live_before:
                        sub['was_live'] = False
                        print(f"Kick yayını sona erdi: {username}")

                elif sub['type'] in ['youtube', 'rss']:
                    # ... (RSS/YouTube kodu aynı)
                    # ...

            except Exception as e:
                print(f"Bir abonelik işlenirken hata oluştu ({sub.get('id')}): {e}")

    save_subscriptions(subscriptions)

# Bot'u çalıştır
bot.run(TOKEN)