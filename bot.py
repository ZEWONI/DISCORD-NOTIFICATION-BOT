import discord
from discord.ext import tasks, commands
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
from typing import Optional, Dict, List
import time as time_module

# Optional: Twitter support
try:
    import tweepy
    TWITTER_AVAILABLE = True
except ImportError:
    TWITTER_AVAILABLE = False
    print("⚠️ Tweepy not installed - Twitter features disabled")

# ==================== CONFIG SYSTEM ====================
class Config:
    def __init__(self):
        load_dotenv()
        self.TOKEN = os.getenv('DISCORD_TOKEN')
        self.TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')
        self.CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL_SECONDS', '30'))
        self.SUBS_FILE = os.getenv('SUBS_FILE', 'subscriptions.json')
        self.CONFIG_FILE = os.getenv('CONFIG_FILE', 'bot_config.json')
        self.STATS_FILE = os.getenv('STATS_FILE', 'bot_stats.json')
        self.NOTIFICATION_SOUND = os.getenv('NOTIFICATION_SOUND', 'notif.mp3')
        self.DEFAULT_LANGUAGE = os.getenv('DEFAULT_LANGUAGE', 'tr')
        self.TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true'
        
        # Load bot config
        self.bot_config = self.load_bot_config()
        
    def load_bot_config(self) -> dict:
        """Load or create bot configuration"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        # Default config
        default_config = {
            'voice_channels': {},  # guild_id: voice_channel_id
            'notification_roles': {},  # guild_id: {type: role_id}
            'filters': {},  # sub_id: {keywords: [], min_viewers: 0, categories: []}
            'custom_messages': {},  # sub_id: {title: "", description: ""}
            'languages': {}  # guild_id: language_code
        }
        self.save_bot_config(default_config)
        return default_config
    
    def save_bot_config(self, config: dict):
        """Save bot configuration"""
        with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        self.bot_config = config

config = Config()

# ==================== LANGUAGE SYSTEM ====================
TRANSLATIONS = {
    'tr': {
        'live_now': '🔴 {user} şimdi yayında!',
        'new_content': '🆕 Yeni İçerik: {title}',
        'help_title': '📋 Yardım Menüsü',
        'help_desc': 'YouTube, Kick, Twitter ve RSS feed takibi için bildirim botu',
        'added': '✅ Eklendi',
        'removed': '✅ Silindi',
        'already_exists': '⚠️ Zaten takip ediliyor',
        'invalid': '❌ Geçersiz',
        'no_subs': '📭 Aktif abonelik yok',
        'category': 'Kategori',
        'viewers': 'İzleyici',
        'uptime': '⏱️ Çalışma Süresi',
        'total_notifications': '📊 Toplam Bildirim',
        'active_subs': '📋 Aktif Abonelik',
        'test_notification': '🧪 Test Bildirimi',
        'test_desc': 'Bu bir test bildirimidir. Sistem çalışıyor!',
        'voice_joined': '🔊 Sesli kanala bağlanıldı',
        'voice_set': '✅ Sesli kanal ayarlandı',
        'role_set': '✅ Rol ayarlandı',
        'filter_set': '✅ Filtre ayarlandı',
        'custom_msg_set': '✅ Özel mesaj ayarlandı',
        'language_set': '✅ Dil değiştirildi',
        'summary_title': '📊 Özet Rapor',
        'last_24h': 'Son 24 Saat',
        'last_7d': 'Son 7 Gün',
        'last_30d': 'Son 30 Gün',
    },
    'en': {
        'live_now': '🔴 {user} is now live!',
        'new_content': '🆕 New Content: {title}',
        'help_title': '📋 Help Menu',
        'help_desc': 'Notification bot for YouTube, Kick, Twitter and RSS feeds',
        'added': '✅ Added',
        'removed': '✅ Removed',
        'already_exists': '⚠️ Already subscribed',
        'invalid': '❌ Invalid',
        'no_subs': '📭 No active subscriptions',
        'category': 'Category',
        'viewers': 'Viewers',
        'uptime': '⏱️ Uptime',
        'total_notifications': '📊 Total Notifications',
        'active_subs': '📋 Active Subscriptions',
        'test_notification': '🧪 Test Notification',
        'test_desc': 'This is a test notification. System is working!',
        'voice_joined': '🔊 Joined voice channel',
        'voice_set': '✅ Voice channel set',
        'role_set': '✅ Role set',
        'filter_set': '✅ Filter set',
        'custom_msg_set': '✅ Custom message set',
        'language_set': '✅ Language changed',
        'summary_title': '📊 Summary Report',
        'last_24h': 'Last 24 Hours',
        'last_7d': 'Last 7 Days',
        'last_30d': 'Last 30 Days',
    }
}

def get_text(key: str, guild_id: int, **kwargs) -> str:
    """Get translated text"""
    lang = config.bot_config.get('languages', {}).get(str(guild_id), config.DEFAULT_LANGUAGE)
    text = TRANSLATIONS.get(lang, TRANSLATIONS['tr']).get(key, key)
    return text.format(**kwargs) if kwargs else text

# ==================== STATS SYSTEM ====================
class Stats:
    def __init__(self):
        self.data = self.load_stats()
        self.start_time = time_module.time()
    
    def load_stats(self) -> dict:
        if os.path.exists(config.STATS_FILE):
            try:
                with open(config.STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'total_notifications': 0,
            'notifications_by_type': {},
            'history': []  # {timestamp, type, title, channel_id}
        }
    
    def save_stats(self):
        with open(config.STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)
    
    def add_notification(self, notif_type: str, title: str, channel_id: int):
        self.data['total_notifications'] += 1
        self.data['notifications_by_type'][notif_type] = self.data['notifications_by_type'].get(notif_type, 0) + 1
        self.data['history'].append({
            'timestamp': datetime.now().isoformat(),
            'type': notif_type,
            'title': title,
            'channel_id': channel_id
        })
        # Keep only last 100 notifications
        if len(self.data['history']) > 100:
            self.data['history'] = self.data['history'][-100:]
        self.save_stats()
    
    def get_summary(self, hours: int = 24) -> Dict:
        cutoff = datetime.now().timestamp() - (hours * 3600)
        recent = [h for h in self.data['history'] 
                  if datetime.fromisoformat(h['timestamp']).timestamp() > cutoff]
        
        summary = {
            'total': len(recent),
            'by_type': {}
        }
        for notif in recent:
            notif_type = notif['type']
            summary['by_type'][notif_type] = summary['by_type'].get(notif_type, 0) + 1
        
        return summary

stats = Stats()

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = False  # Gerekirse True yap
intents.guilds = True
intents.voice_states = True
# intents.members = False  # Kullanmıyoruz
# intents.presences = False  # Kullanmıyoruz

bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

# Cache
_subscriptions_cache = None
_cache_lock = asyncio.Lock()
_voice_clients = {}  # guild_id: voice_client

# ==================== DATA MANAGEMENT ====================
def load_subscriptions():
    global _subscriptions_cache
    if _subscriptions_cache is not None:
        return _subscriptions_cache
    
    if not os.path.exists(config.SUBS_FILE):
        _subscriptions_cache = []
        return []
    
    try:
        with open(config.SUBS_FILE, 'r', encoding='utf-8') as f:
            _subscriptions_cache = json.load(f)
            return _subscriptions_cache
    except:
        _subscriptions_cache = []
        return []

async def save_subscriptions(subscriptions):
    global _subscriptions_cache
    async with _cache_lock:
        _subscriptions_cache = subscriptions
        await asyncio.to_thread(_write_subs_file, subscriptions)

def _write_subs_file(subscriptions):
    with open(config.SUBS_FILE, 'w', encoding='utf-8') as f:
        json.dump(subscriptions, f, indent=2)

# ==================== SELENIUM ====================
def get_kick_channel_data_with_driver(driver, username):
    try:
        api_url = f"https://kick.com/api/v2/channels/{username}"
        driver.get(api_url)
        
        wait = WebDriverWait(driver, 8)
        body_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        json_text = body_element.text
        
        return json.loads(json_text)
    except Exception as e:
        print(f"[Kick API] {username}: {e}")
        return None

# ==================== TWITTER CLIENT ====================
class TwitterClient:
    def __init__(self):
        self.client = None
        if not TWITTER_AVAILABLE:
            print("⚠️ Twitter features unavailable - install tweepy")
            return
        
        if config.TWITTER_BEARER_TOKEN:
            try:
                self.client = tweepy.Client(bearer_token=config.TWITTER_BEARER_TOKEN)
            except Exception as e:
                print(f"[Twitter] Init failed: {e}")
    
    async def get_user_tweets(self, username: str, last_tweet_id: Optional[str] = None):
        if not self.client or not TWITTER_AVAILABLE:
            return None
        
        try:
            user = await asyncio.to_thread(
                self.client.get_user, 
                username=username,
                user_fields=['profile_image_url']
            )
            
            if not user.data:
                return None
            
            tweets = await asyncio.to_thread(
                self.client.get_users_tweets,
                id=user.data.id,
                max_results=5,
                tweet_fields=['created_at', 'text'],
                since_id=last_tweet_id
            )
            
            return {
                'user': user.data,
                'tweets': tweets.data if tweets.data else []
            }
        except Exception as e:
            print(f"[Twitter] {username}: {e}")
            return None

twitter_client = TwitterClient()

# ==================== VOICE NOTIFICATION ====================
async def play_notification_sound(guild_id: int):
    """Play notification sound in voice channel"""
    try:
        voice_channel_id = config.bot_config.get('voice_channels', {}).get(str(guild_id))
        if not voice_channel_id:
            return
        
        voice_channel = bot.get_channel(int(voice_channel_id))
        if not voice_channel:
            return
        
        # Check if already connected
        voice_client = _voice_clients.get(guild_id)
        
        if not voice_client or not voice_client.is_connected():
            voice_client = await voice_channel.connect()
            _voice_clients[guild_id] = voice_client
        
        # Play sound if file exists
        if os.path.exists(config.NOTIFICATION_SOUND):
            if not voice_client.is_playing():
                source = discord.FFmpegPCMAudio(config.NOTIFICATION_SOUND)
                voice_client.play(source)
    except Exception as e:
        print(f"[Voice] {guild_id}: {e}")

# ==================== FILTERS ====================
def check_filters(sub: dict, data: dict) -> bool:
    """Check if notification should be sent based on filters"""
    sub_id = sub.get('id')
    filters = config.bot_config.get('filters', {}).get(sub_id)
    
    if not filters:
        return True
    
    # Check minimum viewers (Kick only)
    if 'min_viewers' in filters and sub['type'] == 'kick':
        livestream = data.get('livestream', {})
        viewers = livestream.get('viewer_count', 0)
        if viewers < filters['min_viewers']:
            return False
    
    # Check categories
    if 'categories' in filters and filters['categories']:
        if sub['type'] == 'kick':
            livestream = data.get('livestream', {})
            categories = livestream.get('categories', [])
            category_names = [c.get('name', '').lower() for c in categories]
            if not any(cat.lower() in category_names for cat in filters['categories']):
                return False
    
    # Check keywords
    if 'keywords' in filters and filters['keywords']:
        title = ""
        if sub['type'] == 'kick':
            livestream = data.get('livestream', {})
            title = livestream.get('session_title', '').lower()
        elif 'title' in data:
            title = data['title'].lower()
        
        if title and not any(keyword.lower() in title for keyword in filters['keywords']):
            return False
    
    return True

# ==================== CUSTOM MESSAGES ====================
def get_custom_embed(sub: dict, default_embed: discord.Embed) -> discord.Embed:
    """Get custom embed if configured"""
    sub_id = sub.get('id')
    custom_msg = config.bot_config.get('custom_messages', {}).get(sub_id)
    
    if not custom_msg:
        return default_embed
    
    if 'title' in custom_msg:
        default_embed.title = custom_msg['title']
    if 'description' in custom_msg:
        default_embed.description = custom_msg['description']
    if 'color' in custom_msg:
        default_embed.color = int(custom_msg['color'], 16)
    
    return default_embed

# ==================== MENTION HELPER ====================
def get_mention_string(guild_id: int, notif_type: str) -> str:
    """Get mention string based on role configuration"""
    roles = config.bot_config.get('notification_roles', {}).get(str(guild_id), {})
    role_id = roles.get(notif_type)
    
    if role_id:
        return f"<@&{role_id}>"
    
    return "@everyone"

# ==================== BOT EVENTS ====================
@bot.event
async def on_ready():
    print(f'✅ {bot.user} aktif')
    print(f'🌍 Dil: {config.DEFAULT_LANGUAGE.upper()}')
    print(f'⏱️ Kontrol: {config.CHECK_INTERVAL}s')
    print(f'🧪 Test Modu: {config.TEST_MODE}')
    
    # Auto-migrate old subscriptions (add guild_id)
    await migrate_old_subscriptions()
    
    try:
        await asyncio.to_thread(GeckoDriverManager().install)
        print("✅ GeckoDriver hazır")
    except Exception as e:
        print(f"❌ GeckoDriver: {e}")
    
    await tree.sync()
    check_feeds.start()
    
    # Join voice channels on startup
    for guild_id_str, voice_channel_id in config.bot_config.get('voice_channels', {}).items():
        try:
            voice_channel = bot.get_channel(int(voice_channel_id))
            if voice_channel:
                voice_client = await voice_channel.connect()
                _voice_clients[int(guild_id_str)] = voice_client
                print(f"🔊 Sesli kanala bağlanıldı: {voice_channel.name}")
        except Exception as e:
            print(f"[Voice Connect] {guild_id_str}: {e}")
    
    print("✅ Bot hazır!")

async def migrate_old_subscriptions():
    """Auto-migrate old subscriptions without guild_id"""
    subscriptions = load_subscriptions()
    changed = False
    
    for sub in subscriptions:
        # Skip if already has guild_id
        if sub.get('guild_id'):
            continue
        
        # Try to find guild from channel_id
        channel_id = sub.get('discord_channel_id')
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel and hasattr(channel, 'guild'):
                sub['guild_id'] = channel.guild.id
                changed = True
                print(f"🔄 Migration: {sub.get('id', 'unknown')[:30]} → Guild {channel.guild.name}")
    
    if changed:
        await save_subscriptions(subscriptions)
        print(f"✅ {sum(1 for s in subscriptions if s.get('guild_id'))} abonelik migration tamamlandı")
    else:
        print("ℹ️ Migration gerekmiyor")

@bot.event
async def on_voice_state_update(member, before, after):
    """Rejoin voice channel if disconnected"""
    if member.id != bot.user.id:
        return
    
    # If bot was disconnected
    if before.channel and not after.channel:
        guild_id = before.channel.guild.id
        voice_channel_id = config.bot_config.get('voice_channels', {}).get(str(guild_id))
        
        if voice_channel_id:
            try:
                await asyncio.sleep(3)  # Wait before reconnecting
                voice_channel = bot.get_channel(int(voice_channel_id))
                if voice_channel:
                    voice_client = await voice_channel.connect()
                    _voice_clients[guild_id] = voice_client
                    print(f"🔊 Sesli kanala yeniden bağlanıldı: {voice_channel.name}")
            except Exception as e:
                print(f"[Voice Reconnect] {guild_id}: {e}")

# ==================== SLASH COMMANDS ====================
@tree.command(name="help", description="Bot komutları")
async def help_cmd(interaction: discord.Interaction):
    lang = config.bot_config.get('languages', {}).get(str(interaction.guild_id), config.DEFAULT_LANGUAGE)
    
    embed = discord.Embed(
        title=get_text('help_title', interaction.guild_id),
        description=get_text('help_desc', interaction.guild_id),
        color=discord.Color.blue()
    )
    
    commands_list = {
        'tr': [
            ('🎮 /kick_ekle', 'Kick kanalı takip et'),
            ('🎥 /youtube_ekle', 'YouTube kanalı takip et'),
            ('📰 /feed_ekle', 'RSS feed takip et'),
            ('🐦 /twitter_ekle', 'Twitter hesabı takip et'),
            ('📜 /abonelikleri_listele', 'Abonelikleri listele'),
            ('🗑️ /abonelik_sil', 'Abonelik sil'),
            ('🔊 /sesli_kanal_ayarla', 'Bildirim için sesli kanal'),
            ('👥 /rol_ayarla', 'Bildirim rolü ayarla'),
            ('🎯 /filtre_ayarla', 'Abonelik filtresi'),
            ('🎨 /ozel_mesaj', 'Özel bildirim mesajı'),
            ('📊 /ozet', 'İstatistik özeti'),
            ('📈 /istatistikler', 'Bot istatistikleri'),
            ('🌍 /dil', 'Dil değiştir (tr/en)'),
            ('🧪 /test', 'Test bildirimi gönder'),
        ],
        'en': [
            ('🎮 /kick_ekle', 'Follow Kick channel'),
            ('🎥 /youtube_ekle', 'Follow YouTube channel'),
            ('📰 /feed_ekle', 'Follow RSS feed'),
            ('🐦 /twitter_ekle', 'Follow Twitter account'),
            ('📜 /abonelikleri_listele', 'List subscriptions'),
            ('🗑️ /abonelik_sil', 'Delete subscription'),
            ('🔊 /sesli_kanal_ayarla', 'Set voice channel'),
            ('👥 /rol_ayarla', 'Set notification role'),
            ('🎯 /filtre_ayarla', 'Set subscription filter'),
            ('🎨 /ozel_mesaj', 'Custom notification message'),
            ('📊 /ozet', 'Statistics summary'),
            ('📈 /istatistikler', 'Bot statistics'),
            ('🌍 /dil', 'Change language (tr/en)'),
            ('🧪 /test', 'Send test notification'),
        ]
    }
    
    for name, desc in commands_list.get(lang, commands_list['tr']):
        embed.add_field(name=name, value=desc, inline=False)
    
    embed.set_footer(text=f"v2.0 | {config.CHECK_INTERVAL}s interval")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="kick_ekle", description="Kick kanalı takip et")
async def kick_add(interaction: discord.Interaction, kullanici_adi: str, kanal: discord.TextChannel):
    kullanici_adi = kullanici_adi.lower().strip()
    subscriptions = load_subscriptions()
    
    if any(s.get('type') == 'kick' and s.get('username') == kullanici_adi and s['discord_channel_id'] == kanal.id for s in subscriptions):
        await interaction.response.send_message(
            get_text('already_exists', interaction.guild_id),
            ephemeral=True
        )
        return
    
    new_sub = {
        'type': 'kick',
        'id': f"kick_{kullanici_adi}",
        'username': kullanici_adi,
        'discord_channel_id': kanal.id,
        'guild_id': interaction.guild_id,
        'was_live': False
    }
    subscriptions.append(new_sub)
    await save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ Kick: `{kullanici_adi}` → <#{kanal.id}>")

@tree.command(name="youtube_ekle", description="YouTube kanalı takip et")
async def youtube_add(interaction: discord.Interaction, channel_id: str, kanal: discord.TextChannel):
    channel_id = channel_id.strip()
    
    if not channel_id.startswith("UC"):
        await interaction.response.send_message(get_text('invalid', interaction.guild_id) + " (UC)", ephemeral=True)
        return
    
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    subscriptions = load_subscriptions()
    
    if any(s.get('url') == feed_url and s['discord_channel_id'] == kanal.id for s in subscriptions):
        await interaction.response.send_message(get_text('already_exists', interaction.guild_id), ephemeral=True)
        return
    
    new_sub = {
        'type': 'youtube',
        'id': channel_id,
        'url': feed_url,
        'discord_channel_id': kanal.id,
        'guild_id': interaction.guild_id,
        'last_entry_id': None
    }
    subscriptions.append(new_sub)
    await save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ YouTube: `{channel_id}` → <#{kanal.id}>")

@tree.command(name="feed_ekle", description="RSS/Atom feed takip et")
async def feed_add(interaction: discord.Interaction, feed_url: str, kanal: discord.TextChannel):
    feed_url = feed_url.strip()
    subscriptions = load_subscriptions()
    
    if any(s.get('url') == feed_url and s['discord_channel_id'] == kanal.id for s in subscriptions):
        await interaction.response.send_message(get_text('already_exists', interaction.guild_id), ephemeral=True)
        return
    
    new_sub = {
        'type': 'rss',
        'id': feed_url,
        'url': feed_url,
        'discord_channel_id': kanal.id,
        'guild_id': interaction.guild_id,
        'last_entry_id': None
    }
    subscriptions.append(new_sub)
    await save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ RSS: `{feed_url}` → <#{kanal.id}>")

@tree.command(name="twitter_ekle", description="Twitter hesabı takip et")
async def twitter_add(interaction: discord.Interaction, kullanici_adi: str, kanal: discord.TextChannel):
    if not TWITTER_AVAILABLE:
        await interaction.response.send_message("❌ Tweepy kurulu değil. Kurmak için: `pip install tweepy`", ephemeral=True)
        return
    
    if not config.TWITTER_BEARER_TOKEN:
        await interaction.response.send_message("❌ Twitter API yapılandırılmamış", ephemeral=True)
        return
    
    kullanici_adi = kullanici_adi.strip().replace('@', '')
    subscriptions = load_subscriptions()
    
    if any(s.get('type') == 'twitter' and s.get('username') == kullanici_adi and s['discord_channel_id'] == kanal.id for s in subscriptions):
        await interaction.response.send_message(get_text('already_exists', interaction.guild_id), ephemeral=True)
        return
    
    new_sub = {
        'type': 'twitter',
        'id': f"twitter_{kullanici_adi}",
        'username': kullanici_adi,
        'discord_channel_id': kanal.id,
        'guild_id': interaction.guild_id,
        'last_tweet_id': None
    }
    subscriptions.append(new_sub)
    await save_subscriptions(subscriptions)
    await interaction.response.send_message(f"✅ Twitter: `@{kullanici_adi}` → <#{kanal.id}>")

@tree.command(name="abonelikleri_listele", description="Tüm abonelikleri listele")
async def list_subs(interaction: discord.Interaction):
    subscriptions = load_subscriptions()
    
    # Backward compatibility: filter by guild OR show all if no guild_id exists
    guild_subs = [s for s in subscriptions if s.get('guild_id') == interaction.guild_id or not s.get('guild_id')]
    
    if not guild_subs:
        await interaction.response.send_message(get_text('no_subs', interaction.guild_id), ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 Aktif Abonelikler", color=discord.Color.orange())
    
    lines = []
    for i, sub in enumerate(guild_subs, 1):
        channel = bot.get_channel(sub['discord_channel_id'])
        ch_mention = f"<#{channel.id}>" if channel else "❌"
        sub_id = sub.get('username') or sub.get('id', 'N/A')
        
        # Show filters if any
        filters = config.bot_config.get('filters', {}).get(sub.get('id'))
        filter_info = ""
        if filters:
            filter_info = " 🎯"
        
        lines.append(f"**{i}.** `{sub['type'].upper()}`: `{sub_id}`{filter_info} → {ch_mention}")
    
    embed.description = '\n'.join(lines)
    embed.set_footer(text=f"Toplam: {len(guild_subs)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="abonelik_sil", description="Abonelik sil")
async def del_sub(interaction: discord.Interaction, numara: int):
    subscriptions = load_subscriptions()
    
    # Backward compatibility: filter by guild OR show all if no guild_id exists
    guild_subs = [s for s in subscriptions if s.get('guild_id') == interaction.guild_id or not s.get('guild_id')]
    
    index = numara - 1
    if not (0 <= index < len(guild_subs)):
        await interaction.response.send_message(get_text('invalid', interaction.guild_id), ephemeral=True)
        return
    
    removed = guild_subs[index]
    subscriptions = [s for s in subscriptions if s != removed]
    await save_subscriptions(subscriptions)
    
    sub_id = removed.get('username') or removed.get('id', 'N/A')
    await interaction.response.send_message(f"{get_text('removed', interaction.guild_id)}: `{sub_id}`")

@tree.command(name="sesli_kanal_ayarla", description="Bildirim için sesli kanal ayarla")
async def set_voice(interaction: discord.Interaction, kanal: discord.VoiceChannel):
    config.bot_config.setdefault('voice_channels', {})[str(interaction.guild_id)] = kanal.id
    config.save_bot_config(config.bot_config)
    
    # Join voice channel
    try:
        voice_client = await kanal.connect()
        _voice_clients[interaction.guild_id] = voice_client
        await interaction.response.send_message(f"{get_text('voice_set', interaction.guild_id)}: {kanal.mention}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Hata: {e}", ephemeral=True)

@tree.command(name="rol_ayarla", description="Bildirim rolü ayarla")
async def set_role(interaction: discord.Interaction, tip: str, rol: discord.Role):
    if tip not in ['kick', 'youtube', 'rss', 'twitter']:
        await interaction.response.send_message("❌ Geçersiz tip (kick/youtube/rss/twitter)", ephemeral=True)
        return
    
    config.bot_config.setdefault('notification_roles', {}).setdefault(str(interaction.guild_id), {})[tip] = rol.id
    config.save_bot_config(config.bot_config)
    
    await interaction.response.send_message(f"{get_text('role_set', interaction.guild_id)}: {rol.mention} → `{tip}`")

@tree.command(name="filtre_ayarla", description="Abonelik filtresi ayarla")
async def set_filter(interaction: discord.Interaction, abonelik_id: str, min_izleyici: int = 0, kategoriler: str = "", anahtar_kelimeler: str = ""):
    subscriptions = load_subscriptions()
    sub = next((s for s in subscriptions if s.get('id') == abonelik_id or s.get('username') == abonelik_id), None)
    
    if not sub:
        await interaction.response.send_message("❌ Abonelik bulunamadı", ephemeral=True)
        return
    
    filter_config = {}
    
    if min_izleyici > 0:
        filter_config['min_viewers'] = min_izleyici
    
    if kategoriler:
        filter_config['categories'] = [c.strip() for c in kategoriler.split(',')]
    
    if anahtar_kelimeler:
        filter_config['keywords'] = [k.strip() for k in anahtar_kelimeler.split(',')]
    
    config.bot_config.setdefault('filters', {})[sub['id']] = filter_config
    config.save_bot_config(config.bot_config)
    
    await interaction.response.send_message(f"{get_text('filter_set', interaction.guild_id)}: `{abonelik_id}`")

@tree.command(name="ozel_mesaj", description="Özel bildirim mesajı ayarla")
async def custom_msg(interaction: discord.Interaction, abonelik_id: str, baslik: str = "", aciklama: str = "", renk: str = ""):
    subscriptions = load_subscriptions()
    sub = next((s for s in subscriptions if s.get('id') == abonelik_id or s.get('username') == abonelik_id), None)
    
    if not sub:
        await interaction.response.send_message("❌ Abonelik bulunamadı", ephemeral=True)
        return
    
    custom_config = {}
    
    if baslik:
        custom_config['title'] = baslik
    
    if aciklama:
        custom_config['description'] = aciklama
    
    if renk:
        custom_config['color'] = renk.replace('#', '')
    
    config.bot_config.setdefault('custom_messages', {})[sub['id']] = custom_config
    config.save_bot_config(config.bot_config)
    
    await interaction.response.send_message(f"{get_text('custom_msg_set', interaction.guild_id)}: `{abonelik_id}`")

@tree.command(name="ozet", description="İstatistik özeti")
async def summary(interaction: discord.Interaction, sure: int = 24):
    if sure not in [24, 168, 720]:  # 24h, 7d, 30d
        await interaction.response.send_message("❌ Geçersiz süre (24/168/720 saat)", ephemeral=True)
        return
    
    summary_data = stats.get_summary(sure)
    
    embed = discord.Embed(
        title=get_text('summary_title', interaction.guild_id),
        color=discord.Color.blue()
    )
    
    period_name = {
        24: get_text('last_24h', interaction.guild_id),
        168: get_text('last_7d', interaction.guild_id),
        720: get_text('last_30d', interaction.guild_id)
    }
    
    embed.add_field(name="📅 Dönem", value=period_name[sure], inline=False)
    embed.add_field(name="📊 Toplam Bildirim", value=str(summary_data['total']), inline=True)
    
    if summary_data['by_type']:
        type_str = '\n'.join([f"`{t.upper()}`: {c}" for t, c in summary_data['by_type'].items()])
        embed.add_field(name="📈 Tiplere Göre", value=type_str, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="istatistikler", description="Bot istatistikleri")
async def bot_stats(interaction: discord.Interaction):
    uptime_seconds = int(time_module.time() - stats.start_time)
    uptime_str = f"{uptime_seconds // 3600}s {(uptime_seconds % 3600) // 60}d"
    
    subscriptions = load_subscriptions()
    guild_subs = [s for s in subscriptions if s.get('guild_id') == interaction.guild_id]
    
    embed = discord.Embed(title="📊 Bot İstatistikleri", color=discord.Color.green())
    embed.add_field(name=get_text('uptime', interaction.guild_id), value=uptime_str, inline=True)
    embed.add_field(name=get_text('total_notifications', interaction.guild_id), value=str(stats.data['total_notifications']), inline=True)
    embed.add_field(name=get_text('active_subs', interaction.guild_id), value=str(len(guild_subs)), inline=True)
    
    # Voice status
    voice_connected = interaction.guild_id in _voice_clients and _voice_clients[interaction.guild_id].is_connected()
    embed.add_field(name="🔊 Sesli Kanal", value="✅ Bağlı" if voice_connected else "❌ Bağlı değil", inline=True)
    
    # Recent notifications
    recent = stats.data['history'][-5:]
    if recent:
        recent_str = '\n'.join([f"`{n['type']}`: {n['title'][:30]}..." for n in reversed(recent)])
        embed.add_field(name="📜 Son Bildirimler", value=recent_str, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="dil", description="Dil değiştir")
async def change_lang(interaction: discord.Interaction, dil: str):
    if dil not in ['tr', 'en']:
        await interaction.response.send_message("❌ Geçersiz dil (tr/en)", ephemeral=True)
        return
    
    config.bot_config.setdefault('languages', {})[str(interaction.guild_id)] = dil
    config.save_bot_config(config.bot_config)
    
    await interaction.response.send_message(f"{get_text('language_set', interaction.guild_id)}: `{dil.upper()}`")

@tree.command(name="test", description="Test bildirimi gönder")
async def test_notif(interaction: discord.Interaction, kanal: discord.TextChannel):
    embed = discord.Embed(
        title=get_text('test_notification', interaction.guild_id),
        description=get_text('test_desc', interaction.guild_id),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Test | {datetime.now().strftime('%H:%M:%S')}")
    
    await kanal.send(embed=embed)
    
    # Play sound if configured
    await play_notification_sound(interaction.guild_id)
    
    await interaction.response.send_message(f"✅ Test bildirimi gönderildi: {kanal.mention}", ephemeral=True)

# ==================== BACKGROUND TASKS ====================
@tasks.loop(seconds=config.CHECK_INTERVAL)
async def check_feeds():
    await bot.wait_until_ready()
    subscriptions = load_subscriptions()
    
    if not subscriptions:
        return
    
    if config.TEST_MODE:
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] 🧪 TEST MODE | {len(subscriptions)} subs")
    
    kick_subs = [s for s in subscriptions if s['type'] == 'kick']
    feed_subs = [s for s in subscriptions if s['type'] in ['youtube', 'rss']]
    twitter_subs = [s for s in subscriptions if s['type'] == 'twitter']
    
    tasks_list = []
    if kick_subs:
        tasks_list.append(check_kick_streams(kick_subs))
    if feed_subs:
        tasks_list.append(check_rss_feeds(feed_subs))
    if twitter_subs:
        tasks_list.append(check_twitter_accounts(twitter_subs))
    
    if tasks_list:
        await asyncio.gather(*tasks_list, return_exceptions=True)

# ==================== KICK CHECKER ====================
async def check_kick_streams(kick_subs):
    driver = None
    try:
        options = FirefoxOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.page_load_strategy = 'eager'
        
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
            
            if is_live and not was_live:
                # Check filters
                if not check_filters(sub, {'livestream': livestream}):
                    print(f"🎯 Kick filtre engelledi: {username}")
                    continue
                
                channel = bot.get_channel(sub['discord_channel_id'])
                if channel:
                    user_data = data.get('user', {})
                    
                    embed = discord.Embed(
                        title=get_text('live_now', sub.get('guild_id', 0), user=user_data.get('username', username)),
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
                        embed.add_field(
                            name=get_text('category', sub.get('guild_id', 0)),
                            value=categories[0].get('name', 'N/A'),
                            inline=True
                        )
                    
                    embed.add_field(
                        name=get_text('viewers', sub.get('guild_id', 0)),
                        value=str(livestream.get('viewer_count', 0)),
                        inline=True
                    )
                    embed.set_footer(text="Yayın başladı!")
                    
                    # Custom message
                    embed = get_custom_embed(sub, embed)
                    
                    # Get mention
                    mention = get_mention_string(sub.get('guild_id'), 'kick')
                    
                    await channel.send(f"{mention} `{username}` Kick'te yayın açtı!", embed=embed)
                    
                    # Play sound
                    await play_notification_sound(sub.get('guild_id'))
                    
                    # Stats
                    stats.add_notification('kick', username, channel.id)
                    
                    print(f"✅ Kick: {username}")
                
                for s in subscriptions:
                    if s.get('type') == 'kick' and s.get('username') == username:
                        s['was_live'] = True
                await save_subscriptions(subscriptions)
            
            elif not is_live and was_live:
                for s in subscriptions:
                    if s.get('type') == 'kick' and s.get('username') == username:
                        s['was_live'] = False
                await save_subscriptions(subscriptions)
                print(f"🔵 Kick bitti: {username}")
    
    except Exception as e:
        print(f"❌ Kick: {e}")
    finally:
        if driver:
            await asyncio.to_thread(driver.quit)

# ==================== RSS/YOUTUBE CHECKER ====================
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
            
            if sub.get('last_entry_id') is None:
                subscriptions = load_subscriptions()
                for s in subscriptions:
                    if s.get('id') == sub.get('id'):
                        s['last_entry_id'] = entry_id
                await save_subscriptions(subscriptions)
                return
            
            if sub['last_entry_id'] != entry_id:
                # Check filters
                if not check_filters(sub, {'title': latest.title}):
                    print(f"🎯 {sub['type'].upper()} filtre engelledi: {latest.title[:30]}")
                    # Update ID but don't notify
                    subscriptions = load_subscriptions()
                    for s in subscriptions:
                        if s.get('id') == sub.get('id'):
                            s['last_entry_id'] = entry_id
                    await save_subscriptions(subscriptions)
                    return
                
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
                    
                    img_url = None
                    if 'media_thumbnail' in latest and latest.media_thumbnail:
                        img_url = latest.media_thumbnail[0].get('url')
                    elif 'summary' in latest:
                        match = re.search(r'<img[^>]+src="([^">]+)"', latest.summary)
                        if match:
                            img_url = match.group(1)
                    
                    if img_url:
                        embed.set_image(url=img_url)
                    
                    # Custom message
                    embed = get_custom_embed(sub, embed)
                    
                    # Get mention
                    mention = get_mention_string(sub.get('guild_id'), sub['type'])
                    
                    await channel.send(f"{mention}", embed=embed)
                    
                    # Play sound
                    await play_notification_sound(sub.get('guild_id'))
                    
                    # Stats
                    stats.add_notification(sub['type'], latest.title, channel.id)
                    
                    print(f"✅ {sub['type'].upper()}: {latest.title[:50]}")
                
                subscriptions = load_subscriptions()
                for s in subscriptions:
                    if s.get('id') == sub.get('id'):
                        s['last_entry_id'] = entry_id
                await save_subscriptions(subscriptions)
    
    except asyncio.TimeoutError:
        print(f"⏱️ Timeout: {sub.get('url', 'N/A')[:50]}")
    except Exception as e:
        print(f"❌ Feed ({sub.get('id', 'N/A')[:30]}): {e}")

# ==================== TWITTER CHECKER ====================
async def check_twitter_accounts(twitter_subs):
    for sub in twitter_subs:
        try:
            username = sub['username']
            data = await twitter_client.get_user_tweets(username, sub.get('last_tweet_id'))
            
            if not data or not data['tweets']:
                continue
            
            subscriptions = load_subscriptions()
            
            for tweet in reversed(data['tweets']):  # Oldest first
                if sub.get('last_tweet_id') and tweet.id == sub.get('last_tweet_id'):
                    continue
                
                # Check filters
                if not check_filters(sub, {'title': tweet.text}):
                    print(f"🎯 Twitter filtre engelledi: @{username}")
                    continue
                
                channel = bot.get_channel(sub['discord_channel_id'])
                if channel:
                    embed = discord.Embed(
                        title=f"🐦 @{username}",
                        url=f"https://twitter.com/{username}/status/{tweet.id}",
                        description=tweet.text[:500],
                        color=0x1DA1F2
                    )
                    
                    if hasattr(data['user'], 'profile_image_url'):
                        embed.set_thumbnail(url=data['user'].profile_image_url)
                    
                    embed.set_footer(text=f"Twitter • {tweet.created_at.strftime('%H:%M')}")
                    
                    # Custom message
                    embed = get_custom_embed(sub, embed)
                    
                    # Get mention
                    mention = get_mention_string(sub.get('guild_id'), 'twitter')
                    
                    await channel.send(f"{mention}", embed=embed)
                    
                    # Play sound
                    await play_notification_sound(sub.get('guild_id'))
                    
                    # Stats
                    stats.add_notification('twitter', f"@{username}", channel.id)
                    
                    print(f"✅ Twitter: @{username}")
                
                # Update last tweet
                for s in subscriptions:
                    if s.get('id') == sub.get('id'):
                        s['last_tweet_id'] = tweet.id
                await save_subscriptions(subscriptions)
        
        except Exception as e:
            print(f"❌ Twitter (@{sub.get('username', 'N/A')}): {e}")

# ==================== RUN BOT ====================
if __name__ == "__main__":
    if not config.TOKEN:
        print("❌ DISCORD_TOKEN bulunamadı!")
        exit(1)
    
    bot.run(config.TOKEN)