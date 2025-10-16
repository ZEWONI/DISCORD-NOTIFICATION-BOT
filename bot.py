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

# Selenium Tarayıcı Fonksiyonu
def get_kick_channel_data(username):
    options = FirefoxOptions()
    options.add_argument("--headless")
    options.binary_location = '/usr/bin/firefox-esr'
    driver = None
    data = None
    try:
        driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)
        api_url = f"https://kick.com/api/v2/channels/{username}"
        driver.get(api_url)
        time.sleep(3)
        json_text = driver.find_element(By.TAG_NAME, 'pre').text
        data = json.loads(json_text)
    except Exception as e:
        print(f"Selenium ile Kick verisi alınırken hata: {e}")
    finally:
        if driver:
            driver.quit()
    return data

# --- Veri Saklama Fonksiyonları ---
def load_subscriptions():
    if not os.path.exists(SUBS_FILE): return []
    try:
        with open(SUBS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return []

def save_subscriptions(subscriptions):
    with open(SUBS_FILE, 'w', encoding='utf-8') as f: json.dump(subscriptions, f, indent=4)

@bot.event
async def on_ready():
    print(f'{bot.user} olarak giriş yapıldı.')
    await tree.sync()
    check_feeds.start()
    print("Slash komutları senkronize edildi ve feed kontrol döngüsü başladı.")

# --- Slash Komutları (Değişiklik yok) ---
@tree.command(name="help", description="Bot komutları hakkında bilgi verir.")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Yardım Menüsü - NOTIFICATION BOT", description="Bu bot YouTube, Kick ve web sitelerinden yeni içerikleri takip eder.", color=discord.Color.blue())
    embed.add_field(name="/kick_ekle", value="Bir Kick kanalını takip etmek için kullanılır.\n`kullanici_adi`: Kick yayıncısının kullanıcı adı.\n`kanal`: Bildirimlerin gönderileceği Discord kanalı.", inline=False)
    embed.add_field(name="/youtube_ekle", value="Bir YouTube kanalını takip etmek için kullanılır.\n`channel_id`: YouTube kanalının 'UC...' ile başlayan ID'si.", inline=False)
    embed.add_field(name="/feed_ekle", value="Bir web sitesinin RSS/Atom feed'ini takip etmek için kullanılır.\n`feed_url`: Sitenin RSS adresi.", inline=False)
    embed.add_field(name="/abonelikleri_listele", value="Tüm aktif abonelikleri listeler.", inline=False)
    embed.add_field(name="/abonelik_sil", value="Listeden bir aboneliği numarasını girerek siler.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="kick_ekle", description="Yayın açıldığında bildirim almak için bir Kick kanalını takip et.")
async def kick_ekle(interaction: discord.Interaction, kullanici_adi: str, kanal: discord.TextChannel):
    kullanici_adi = kullanici_adi.lower()
    subscriptions = load_subscriptions()
    for sub in subscriptions:
        if sub.get('type') == 'kick' and sub.get('username') == kullanici_adi and sub['discord_channel_id'] == kanal.id:
            await interaction.response.send_message(f"`{kullanici_adi}` adlı Kick kanalı zaten <#{kanal.id}> kanalında takip ediliyor.", ephemeral=True); return
    new_sub = {'type': 'kick', 'id': f"kick_{kullanici_adi}", 'username': kullanici_adi, 'discord_channel_id': kanal.id, 'was_live': False}
    subscriptions.append(new_sub); save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ Başarılı! Kick kanalı (`{kullanici_adi}`) yayın açtığında artık <#{kanal.id}> kanalına bildirilecek.")

@tree.command(name="youtube_ekle", description="Yeni videolar için bir YouTube kanalını takip et.")
async def youtube_ekle(interaction: discord.Interaction, channel_id: str, kanal: discord.TextChannel):
    if not channel_id.startswith("UC"): await interaction.response.send_message("Lütfen geçerli bir YouTube Kanal ID'si girin ('UC' ile başlar).", ephemeral=True); return
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    subscriptions = load_subscriptions()
    for sub in subscriptions:
        if sub.get('url') == feed_url and sub['discord_channel_id'] == kanal.id: await interaction.response.send_message(f"Bu YouTube kanalı zaten <#{kanal.id}> kanalında takip ediliyor.", ephemeral=True); return
    new_sub = {'type': 'youtube','id': channel_id,'url': feed_url,'discord_channel_id': kanal.id,'last_entry_id': None}
    subscriptions.append(new_sub); save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ Başarılı! YouTube kanalı (`{channel_id}`) artık <#{kanal.id}> kanalına bildirilecek.")

@tree.command(name="feed_ekle", description="Yeni yazılar için bir web sitesi RSS/Atom feed'ini takip et.")
async def feed_ekle(interaction: discord.Interaction, feed_url: str, kanal: discord.TextChannel):
    subscriptions = load_subscriptions()
    for sub in subscriptions:
        if sub.get('url') == feed_url and sub['discord_channel_id'] == kanal.id: await interaction.response.send_message(f"Bu feed zaten <#{kanal.id}> kanalında takip ediliyor.", ephemeral=True); return
    new_sub = {'type': 'rss', 'id': feed_url, 'url': feed_url, 'discord_channel_id': kanal.id, 'last_entry_id': None}
    subscriptions.append(new_sub); save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ Başarılı! Feed (`{feed_url}`) artık <#{kanal.id}> kanalına bildirilecek.")

@tree.command(name="abonelikleri_listele", description="Tüm aktif abonelikleri gösterir.")
async def abonelikleri_listele(interaction: discord.Interaction):
    subscriptions = load_subscriptions()
    if not subscriptions: await interaction.response.send_message("Takip edilen hiçbir abonelik bulunmuyor.", ephemeral=True); return
    embed = discord.Embed(title="Aktif Abonelikler", color=discord.Color.orange())
    description_text = ""
    for i, sub in enumerate(subscriptions):
        channel = bot.get_channel(sub['discord_channel_id'])
        channel_mention = f"<#{channel.id}>" if channel else "Bilinmeyen Kanal"
        sub_id = sub.get('username') or sub.get('id')
        description_text += f"**{i+1}.** `{sub['type'].upper()}`: `{sub_id}` -> {channel_mention}\n"
    embed.description = description_text
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="abonelik_sil", description="Bir aboneliği listedeki numarasına göre siler.")
async def abonelik_sil(interaction: discord.Interaction, numara: int):
    subscriptions = load_subscriptions()
    index = numara - 1
    if 0 <= index < len(subscriptions):
        removed_sub = subscriptions.pop(index)
        save_subscriptions(subscriptions)
        sub_id = removed_sub.get('username') or removed_sub.get('id')
        await interaction.response.send_message(f"✅ `{sub_id}` aboneliği başarıyla silindi.", ephemeral=True)
    else: await interaction.response.send_message("Geçersiz numara. Lütfen `/abonelikleri_listele` komutu ile doğru numarayı kontrol edin.", ephemeral=True)

# --- ARKA PLAN GÖREVİ (FEED KONTROLÜ) ---
@tasks.loop(minutes=5)
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
                    data = await bot.loop.run_in_executor(None, get_kick_channel_data, username)
                    if data is None:
                        print(f"Kick verisi alınamadı ({username})."); continue
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
                            # ---> DÜZELTME BURADA: embed=embed olarak değiştirildi
                            await channel.send(f"Hey @everyone! `{data['user']['username']}` Kick'te yayın başlattı!", embed=embed)
                            print(f"Kick bildirimi gönderildi: {data['user']['username']}")
                        sub['was_live'] = True
                        save_subscriptions(subscriptions)
                    elif not is_live_now and was_live_before:
                        sub['was_live'] = False
                        save_subscriptions(subscriptions)
                        print(f"Kick yayını sona erdi: {username}")

                elif sub['type'] in ['youtube', 'rss']:
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
                                # ---> DÜZELTME BURADA: embed=embed olarak değiştirildi
                                await channel.send(embed=embed)
                            sub['last_entry_id'] = entry_id
                            save_subscriptions(subscriptions)
            
            except Exception as e:
                print(f"Bir abonelik işlenirken hata oluştu ({sub.get('id')}): {e}")

bot.run(TOKEN)