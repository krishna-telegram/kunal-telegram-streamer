import os
from os import getenv, environ
from dotenv import load_dotenv

def is_enabled(value, default):
    if value.lower() in ["true", "yes", "1", "enable", "y"]:
        print("✅ Feature enabled")
        return True
    if value.lower() in ["false", "no", "0", "disable", "n"]:
        print("❌ Feature disabled")
        return False
    print(f"⚠️ Invalid value, defaulting to {default}")
    return default

print("🔄 Loading environment variables...")
load_dotenv()

class Var:
    print("🛠️ Initializing bot configuration...")

    MULTI_CLIENT = False
    API_ID = int(getenv('API_ID', ''))
    API_HASH = str(getenv('API_HASH', ''))
    BOT_TOKEN = str(getenv('BOT_TOKEN', ''))
    
    PICS = environ.get('PICS', 'https://i.ibb.co/yBcdL0cc/photo-2026-06-06-21-34-34.jpg').split()
    print(f"📸 Default picture URL: {PICS[0]}")
    
    name = str(getenv('name', 'KunalStreamer'))
    SLEEP_THRESHOLD = int(getenv('SLEEP_THRESHOLD', '60'))
    WORKERS = int(getenv('WORKERS', '4'))
    print(f"🤖 Bot name: {name}\n⏳ Sleep threshold: {SLEEP_THRESHOLD}s\n⚙️ Workers: {WORKERS}")

    BIN_CHANNEL = int(getenv('BIN_CHANNEL', ''))
    NEW_USER_LOG = int(getenv('NEW_USER_LOG', ''))
    print(f"📢 Binary channel ID: {BIN_CHANNEL}\n📝 New user log channel ID: {NEW_USER_LOG}")
    
    PORT = int(getenv('PORT', '8080'))
    BIND_ADDRESS = str(getenv('WEB_SERVER_BIND_ADDRESS', '0.0.0.0'))
    PING_INTERVAL = int(environ.get("PING_INTERVAL", "1200"))
    print(f"🌐 Web server bind address: {BIND_ADDRESS}:{PORT}\n⏰ Ping interval: {PING_INTERVAL}s")
    
    OWNER_ID = [int(x) for x in environ.get("OWNER_ID", "").split()]
    OWNER_USERNAME = str(getenv('OWNER_USERNAME', 'got_nirvana'))
    print(f"👤 Bot owner ID: {OWNER_ID}\n💬 Bot owner username: {OWNER_USERNAME}")
    
    ON_HEROKU = 'DYNO' in environ
    print("🚀 Bot is deployed on Heroku" if ON_HEROKU else "🏠 Bot is running locally")

    # --- AUTO-FETCH HEROKU URL LOGIC ---
    # 1. Checks Heroku Dyno Metadata
    # 2. Falls back to APP_NAME config variable
    # 3. Falls back to localhost for local PC testing
    _APP_NAME = environ.get("HEROKU_APP_NAME") or environ.get("APP_NAME")
    
    if _APP_NAME and ON_HEROKU:
        URL = f"https://{_APP_NAME}.herokuapp.com/"
    else:
        URL = getenv('URL', "http://127.0.0.1:8080/")
        
    if not URL.endswith("/"):
        URL += "/"
        
    print(f"🌍 Base URL: {URL}")
    # -----------------------------------

    DATABASE_URL = str(getenv('DATABASE_URL', ''))
    UPDATES_CHANNEL = str(getenv('UPDATES_CHANNEL', '-1004232147781'))
    print(f"📊 Database URL: {DATABASE_URL}\n📢 Updates channel: {UPDATES_CHANNEL}")

    BANNED_CHANNELS = list(set(int(x) for x in str(getenv("BANNED_CHANNELS", "")).split()))
    BAN_CHNL = list(set(int(x) for x in str(getenv("BAN_CHNL", "")).split()))
    BAN_ALERT = str(getenv('BAN_ALERT', '<b>ʏᴏᴜʀ ᴀʀᴇ ʙᴀɴɴᴇᴅ ᴛᴏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ. ᴄᴏɴᴛᴀᴄᴛ @got_nirvana ᴛᴏ ʀᴇsᴏʟᴠᴇ ᴛʜᴇ ɪssᴜᴇ!!</b>'))


    SHORTLINK = is_enabled(getenv('SHORTLINK', 'False'), False)
    SHORTLINK_URL = getenv('SHORTLINK_URL', '')
    SHORTLINK_API = getenv('SHORTLINK_API', '')
    print(f"🔗 Shortlink feature enabled: {SHORTLINK}")
    if SHORTLINK:
        print(f"🖥️ Shortlink URL: {SHORTLINK_URL}\n⚙️ Shortlink API: {SHORTLINK_API}")
