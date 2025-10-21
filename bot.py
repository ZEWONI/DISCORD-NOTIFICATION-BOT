import discord
from discord.ext import tasks
import os
import json
import feedparser
import aiohttp
from dotenv import load_dotenv
from datetime import datetime
import re
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import asyncio

# Konfigürasyon
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUBS_FILE = 'subscriptions.json'
CHECK_INTERVAL_SECONDS = 30  # Kontrol süresi 30 saniye

# Bot setup
intents = discord.intents.default()
bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

# Cache mekanizması
_subscriptions_cache = None
_cache_lock = asyncio.Lock()

# --- Optimize Edilmiş Veri Saklama ---
def load_subscriptions():
    global _subscriptions_cache
    if _subscriptions_cache is not None:
        return _subscriptions_cache
    
    if not os.path.exists(SUBS_FILE):
        _subscriptions_cache = []
        return []
    
    try:
        with open(SUBS_FILE, 'r', encoding='utf-8') as f:
            _subscriptions_cache = json.load(f)
            return _subscriptions_cache
    except (json.JSONDecodeError, FileNotFoundError):
        _subscriptions_cache = []
        return []

async def save_subscriptions(subscriptions):
    global _subscriptions_cache
    async with _cache_lock:
        _subscriptions_cache = subscriptions
        await asyncio.to_thread(_write_subs_file, subscriptions)

def _write_subs_file(subscriptions):
    with open(SUBS_FILE, 'w', encoding='utf-8') as f:
        json.dump(subscriptions, f, indent=2)

# --- Optimize Edilmiş Selenium Fonksiyonu ---
def get_kick_channel_data_with_driver(driver, username):
    try:
        api_url = f"https://kick.com/api/v2/channels/{username}"
        driver.get(api_url)
        
        wait = WebDriverWait(driver, 8)  # Timeout 10'dan 8'e düşürüldü
        body_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        json_text = body_element.text
        
        return json.loads(json_text)
    except Exception as e:
        print(f"[Kick API Hatası] {username}: {e}")
        return None

# --- Bot Events ---
@bot.event
async def on_ready():
    print(f'✅ {bot.user} aktif')
    
    try:
        await asyncio.to_thread(GeckoDriverManager().install)
        print("✅ GeckoDriver hazır")
    except Exception as e:
        print(f"❌ GeckoDriver hatası: {e}")
    
    await tree.sync()
    check_feeds.start()
    print(f"✅ Slash komutları aktif | Kontrol süresi: {CHECK_INTERVAL_SECONDS}s")

# --- Slash Komutları ---
@tree.command(name="help", description="Bot komutları hakkında bilgi")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Yardım Menüsü",
        description="YouTube, Kick ve RSS feed takibi için bildirim botu",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🎮 /kick_ekle",
        value="Kick yayıncısını takip et\n`kullanici_adi` | `kanal`",
        inline=False
    )
    embed.add_field(
        name="🎥 /youtube_ekle",
        value="YouTube kanalını takip et\n`channel_id` (UC...) | `kanal`",
        inline=False
    )
    embed.add_field(
        name="📰 /feed_ekle",
        value="RSS/Atom feed takip et\n`feed_url` | `kanal`",
        inline=False
    )
    embed.add_field(name="📜 /abonelikleri_listele", value="Tüm abonelikleri göster", inline=False)
    embed.add_field(name="🗑️ /abonelik_sil", value="Abonelik sil (numara ile)", inline=False)
    embed.set_footer(text=f"Kontrol süresi: {CHECK_INTERVAL_SECONDS} saniye")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="kick_ekle", description="Kick kanalı takip et")
async def kick_ekle(interaction: discord.Interaction, kullanici_adi: str, kanal: discord.TextChannel):
    kullanici_adi = kullanici_adi.lower().strip()
    subscriptions = load_subscriptions()
    
    # Duplicate kontrolü
    if any(s.get('type') == 'kick' and s.get('username') == kullanici_adi and s['discord_channel_id'] == kanal.id for s in subscriptions):
        await interaction.response.send_message(f"⚠️ `{kullanici_adi}` zaten <#{kanal.id}>'de takip ediliyor", ephemeral=True)
        return
    
    new_sub = {
        'type': 'kick',
        'id': f"kick_{kullanici_adi}",
        'username': kullanici_adi,
        'discord_channel_id': kanal.id,
        'was_live': False
    }
    subscriptions.append(new_sub)
    await save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ Kick: `{kullanici_adi}` → <#{kanal.id}>")

@tree.command(name="youtube_ekle", description="YouTube kanalı takip et")
async def youtube_ekle(interaction: discord.Interaction, channel_id: str, kanal: discord.TextChannel):
    channel_id = channel_id.strip()
    
    if not channel_id.startswith("UC"):
        await interaction.response.send_message("❌ Geçersiz ID (UC ile başlamalı)", ephemeral=True)
        return
    
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    subscriptions = load_subscriptions()
    
    if any(s.get('url') == feed_url and s['discord_channel_id'] == kanal.id for s in subscriptions):
        await interaction.response.send_message(f"⚠️ Bu kanal zaten <#{kanal.id}>'de takip ediliyor", ephemeral=True)
        return
    
    new_sub = {
        'type': 'youtube',
        'id': channel_id,
        'url': feed_url,
        'discord_channel_id': kanal.id,
        'last_entry_id': None
    }
    subscriptions.append(new_sub)
    await save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ YouTube: `{channel_id}` → <#{kanal.id}>")

@tree.command(name="feed_ekle", description="RSS/Atom feed takip et")
async def feed_ekle(interaction: discord.Interaction, feed_url: str, kanal: discord.TextChannel):
    feed_url = feed_url.strip()
    subscriptions = load_subscriptions()
    
    if any(s.get('url') == feed_url and s['discord_channel_id'] == kanal.id for s in subscriptions):
        await interaction.response.send_message(f"⚠️ Bu feed zaten <#{kanal.id}>'de takip ediliyor", ephemeral=True)
        return
    
    new_sub = {
        'type': 'rss',
        'id': feed_url,
        'url': feed_url,
        'discord_channel_id': kanal.id,
        'last_entry_id': None
    }
    subscriptions.append(new_sub)
    await save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ RSS: `{feed_url}` → <#{kanal.id}>")

@tree.command(name="abonelikleri_listele", description="Tüm abonelikleri listele")
async def list_subs(interaction: discord.Interaction):
    subscriptions = load_subscriptions()
    
    if not subscriptions:
        await interaction.response.send_message("📭 Aktif abonelik yok", ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 Aktif Abonelikler", color=discord.Color.orange())
    
    lines = []
    for i, sub in enumerate(subscriptions, 1):
        channel = bot.get_channel(sub['discord_channel_id'])
        ch_mention = f"<#{channel.id}>" if channel else "❌ Silinmiş"
        sub_id = sub.get('username') or sub.get('id', 'N/A')
        lines.append(f"**{i}.** `{sub['type'].upper()}`: `{sub_id}` → {ch_mention}")
    
    embed.description = '\n'.join(lines)
    embed.set_footer(text=f"Toplam: {len(subscriptions)} abonelik")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="abonelik_sil", description="Abonelik sil")
async def del_sub(interaction: discord.Interaction, numara: int):
    subscriptions = load_subscriptions()
    index = numara - 1
    
    if not (0 <= index < len(subscriptions)):
        await interaction.response.send_message("❌ Geçersiz numara. `/abonelikleri_listele` ile kontrol edin", ephemeral=True)
        return
    
    removed = subscriptions.pop(index)
    await save_subscriptions(subscriptions)
    sub_id = removed.get('username') or removed.get('id', 'N/A')
    await interaction.response.send_message(f"✅ `{sub_id}` silindi")

# --- Optimize Edilmiş Arka Plan Kontrolü ---
@tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
async def check_feeds():
    await bot.wait_until_ready()
    subscriptions = load_subscriptions()
    
    if not subscriptions:
        return
    
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] 🔍 {len(subscriptions)} abonelik kontrol ediliyor...")
    
    kick_subs = [s for s in subscriptions if s['type'] == 'kick']
    feed_subs = [s for s in subscriptions if s['type'] in ['youtube', 'rss']]
    
    # Paralel kontrol
    tasks_list = []
    if kick_subs:
        tasks_list.append(check_kick_streams(kick_subs))
    if feed_subs:
        tasks_list.append(check_rss_feeds(feed_subs))
    
    if tasks_list:
        await asyncio.gather(*tasks_list, return_exceptions=True)

# --- Kick Kontrol (Optimize) ---
async def check_kick_streams(kick_subs):
    driver = None
    try:
        options = FirefoxOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.page_load_strategy = 'eager'  # Daha hızlı yükleme
        
        binary = '/usr/lib/firefox-esr/firefox-esr'
        if os.path.exists(binary):
            options.binary_location = binary
        
        driver = await asyncio.to_thread(
            lambda: webdriver.Firefox(service=FirefoxService(), options=options)
        )
        
        subscriptions = load_subscriptions()
        
        for sub in kick_subs:
            username = sub['username']
            data = await asyncio.to_thread(get_kick_channel_data_with_driver, driver, username)
            
            if data is None:
                continue
            
            livestream = data.get('livestream')
            is_live = livestream is not None
            was_live = sub.get('was_live', False)
            
            # Yayın başladı
            if is_live and not was_live:
                channel = bot.get_channel(sub['discord_channel_id'])
                if channel:
                    user_data = data.get('user', {})
                    embed = discord.Embed(
                        title=f"🔴 {user_data.get('username', username)} yayında!",
                        url=f"https://kick.com/{username}",
                        description=f"**{livestream.get('session_title', 'Başlıksız')}**",
                        color=0x53FC18
                    )
                    embed.set_author(name="Kick.com")
                    
                    if user_data.get('profile_pic'):
                        embed.set_thumbnail(url=user_data['profile_pic'])
                    
                    if livestream.get('thumbnail', {}).get('url'):
                        embed.set_image(url=livestream['thumbnail']['url'])
                    
                    categories = livestream.get('categories', [])
                    if categories:
                        embed.add_field(name="Kategori", value=categories[0].get('name', 'N/A'), inline=True)
                    
                    embed.add_field(name="İzleyici", value=str(livestream.get('viewer_count', 0)), inline=True)
                    embed.set_footer(text="Yayın başladı!")
                    
                    await channel.send(f"@everyone `{username}` Kick'te yayın açtı!", embed=embed)
                    print(f"✅ Kick bildirimi: {username}")
                
                # Durumu güncelle
                for s in subscriptions:
                    if s.get('type') == 'kick' and s.get('username') == username:
                        s['was_live'] = True
                await save_subscriptions(subscriptions)
            
            # Yayın bitti
            elif not is_live and was_live:
                for s in subscriptions:
                    if s.get('type') == 'kick' and s.get('username') == username:
                        s['was_live'] = False
                await save_subscriptions(subscriptions)
                print(f"🔵 Kick yayın bitti: {username}")
    
    except Exception as e:
        print(f"❌ Kick kontrol hatası: {e}")
    finally:
        if driver:
            await asyncio.to_thread(driver.quit)

# --- RSS/YouTube Kontrol (Optimize) ---
async def check_rss_feeds(feed_subs):
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [check_single_feed(session, sub) for sub in feed_subs]
        await asyncio.gather(*tasks, return_exceptions=True)

async def check_single_feed(session, sub):
    try:
        async with session.get(sub['url']) as resp:
            if resp.status != 200:
                return
            
            content = await resp.text()
            feed = await asyncio.to_thread(feedparser.parse, content)
            
            if not feed.entries:
                return
            
            latest = feed.entries[0]
            entry_id = latest.get('id') or latest.get('link')
            
            if not entry_id:
                return
            
            # İlk çalıştırma
            if sub.get('last_entry_id') is None:
                subscriptions = load_subscriptions()
                for s in subscriptions:
                    if s.get('id') == sub.get('id'):
                        s['last_entry_id'] = entry_id
                await save_subscriptions(subscriptions)
                return
            
            # Yeni içerik
            if sub['last_entry_id'] != entry_id:
                channel = bot.get_channel(sub['discord_channel_id'])
                if channel:
                    is_youtube = sub['type'] == 'youtube'
                    embed = discord.Embed(
                        title=f"{'🎥' if is_youtube else '📰'} {latest.title}",
                        url=latest.link,
                        description=f"**{feed.feed.get('title', 'Yeni İçerik')}**",
                        color=discord.Color.red() if is_youtube else discord.Color.green()
                    )
                    
                    if 'author' in latest:
                        embed.set_author(name=latest.author)
                    
                    # Görsel ekleme
                    img_url = None
                    if 'media_thumbnail' in latest and latest.media_thumbnail:
                        img_url = latest.media_thumbnail[0].get('url')
                    elif 'summary' in latest:
                        match = re.search(r'<img[^>]+src="([^">]+)"', latest.summary)
                        if match:
                            img_url = match.group(1)
                    
                    if img_url:
                        embed.set_image(url=img_url)
                    
                    await channel.send(embed=embed)
                    print(f"✅ {'YouTube' if is_youtube else 'RSS'} bildirimi: {latest.title[:50]}")
                
                # Güncelle
                subscriptions = load_subscriptions()
                for s in subscriptions:
                    if s.get('id') == sub.get('id'):
                        s['last_entry_id'] = entry_id
                await save_subscriptions(subscriptions)
    
    except asyncio.TimeoutError:
        print(f"⏱️ Timeout: {sub.get('url', 'N/A')[:50]}")
    except Exception as e:
        print(f"❌ Feed hatası ({sub.get('id', 'N/A')[:30]}): {e}")

# Bot başlat
if __name__ == "__main__":
    bot.run(TOKEN)