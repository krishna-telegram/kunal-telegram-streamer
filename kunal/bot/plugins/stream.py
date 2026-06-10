import logging
import asyncio
from urllib.parse import quote_plus
from pyrogram import filters, Client
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from kunal.bot import StreamBot
from kunal.utils.database import Database
from kunal.vars import Var
from kunal.utils.file_properties import get_name, get_hash, get_media_file_size
from kunal.utils.helpers import get_shortlink, humanbytes

# --- Standard Logging Setup for Heroku (No Colors) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)
# -----------------------------------------------------

db = Database(Var.DATABASE_URL, Var.name)
pass_db = Database(Var.DATABASE_URL, "ag_passwords")
pass_dict = {}

msg_text = """
<b>🚀 Link Generated Successfully!</b>

<b>📝 File:</b> <code>{}</code>
<b>📁 Size:</b> <code>{}</code>

<b>🔗 Link Type:</b> Temporary & Encrypted
"""

@StreamBot.on_message((filters.private) & (filters.document | filters.video | filters.audio | filters.photo), group=4)
async def private_receive_handler(c: Client, m: Message):
    if not await db.is_user_exist(m.from_user.id):
        logger.info(f"👤 New user joined: {m.from_user.id} ({m.from_user.first_name})")
        await db.add_user(m.from_user.id)
        await c.send_message(
            Var.NEW_USER_LOG,
            f"#𝐍𝐞𝐰𝐔𝐬𝐞𝐫\n\n**᚛› 𝐍𝐚𝐦𝐞 - [{m.from_user.first_name}](tg://user?id={m.from_user.id})**"
        )
        
    if Var.UPDATES_CHANNEL != "None":
        try:
            user = await c.get_chat_member(Var.UPDATES_CHANNEL, m.chat.id)
            if user.status == "kicked":
                logger.warning(f"🛑 Banned user attempted access: {m.from_user.id}")
                return await c.send_message(chat_id=m.chat.id, text="You are banned!\n\nContact Developer [KUNAL](https://t.me/got_nirvana) he will help you.", disable_web_page_preview=True)
        except UserNotParticipant:
            logger.info(f"🔑 User {m.from_user.id} requested access without joining updates channel.")
            return await c.send_photo(
                chat_id=m.chat.id,
                photo="https://graph.org/file/a8095ab3c9202607e78ad.jpg",
                caption="<b>ᴊᴏɪɴ ᴏᴜʀ ᴜᴘᴅᴀᴛᴇs ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴜꜱᴇ ᴍᴇ</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ᴊᴏɪɴ ɴᴏᴡ 🚩", url=f"https://telegram.me/{Var.UPDATES_CHANNEL}")]])
            )
        except Exception as e:
            logger.error(f"❌ Database/API Error checking participant status for {m.from_user.id}: {e}")
            return await c.send_message(chat_id=m.chat.id, text="sᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ. ᴄᴏɴᴛᴀᴄᴛ ᴍʏ [ʙᴏss](https://t.me/got_nirvana)", disable_web_page_preview=True)

    if await db.is_banned(int(m.from_user.id)):
        logger.warning(f"🛑 Banned user action blocked: {m.from_user.id}")
        return await m.reply(Var.BAN_ALERT)

    try:
        logger.debug(f"📤 Uploading/Copying file to bin channel for user {m.from_user.id}...")
        log_msg = await m.copy(chat_id=Var.BIN_CHANNEL)
        name_quoted = quote_plus(get_name(log_msg))
        hash_val = get_hash(log_msg)

        stream_link = f"{Var.URL}watch/{log_msg.id}/{name_quoted}?hash={hash_val}"
        download_link = f"{Var.URL}{log_msg.id}/{name_quoted}?hash={hash_val}"

        if getattr(Var, 'SHORTLINK', None):
            logger.debug(f"🔄 Generating shortlinks for private request...")
            stream_link, download_link = await asyncio.gather(
                asyncio.to_thread(get_shortlink, stream_link), 
                asyncio.to_thread(get_shortlink, download_link)
            )

        await log_msg.reply_text(
            text=f"ʀᴇǫᴜᴇꜱᴛᴇᴅ ʙʏ : [{m.from_user.first_name}](tg://user?id={m.from_user.id})\nUꜱᴇʀ ɪᴅ : {m.from_user.id}\nStream ʟɪɴᴋ : {stream_link}",
            disable_web_page_preview=True, quote=True
        )
        await m.reply_text(
            text=msg_text.format(get_name(log_msg), humanbytes(get_media_file_size(m))),
            quote=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Stream Now", url=stream_link), InlineKeyboardButton("⬇️ Download", url=download_link)]
            ])
        )
        logger.info(f"✅ Successfully generated links for user {m.from_user.id}")
    except FloodWait as e:
        logger.warning(f"⚠️ Rate limited! Sleeping for {e.value}s before continuing private request.")
        await asyncio.sleep(e.value + 1)
        await c.send_message(chat_id=Var.BIN_CHANNEL, text=f"Gᴏᴛ FʟᴏᴏᴅWᴀɪᴛ ᴏғ {e.value}s from [{m.from_user.first_name}](tg://user?id={m.from_user.id})\n\n**𝚄𝚜𝚎𝚛 𝙸𝙳 :** `{m.from_user.id}`", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"❌ Failed to process private message for {m.from_user.id}: {e}", exc_info=True)

@StreamBot.on_message(filters.channel & ~filters.group & filters.video & ~filters.forwarded, group=-1)
async def channel_receive_handler(bot, broadcast):
    chat_id = int(broadcast.chat.id)

    if chat_id == Var.BIN_CHANNEL:
        return


    if chat_id in getattr(Var, 'BAN_CHNL', []) or chat_id in getattr(Var, 'BANNED_CHANNELS', []) or await db.is_banned(chat_id):
        logger.warning(f"🛑 Detected activity in banned channel {chat_id}. Leaving immediately.")
        return await bot.leave_chat(chat_id)
    try:
        logger.debug(f"📥 Copying new channel video from {chat_id} to bin channel...")
        log_msg = await broadcast.copy(chat_id=Var.BIN_CHANNEL, reply_markup=None)
    except Exception as e:
        logger.error(f"❌ Could not copy media to bin channel: {e}")
        return

    file_name = quote_plus(get_name(log_msg))
    hash_val = get_hash(log_msg)
    stream_link = f"{Var.URL}watch/{log_msg.id}/{file_name}?hash={hash_val}"
    download_link = f"{Var.URL}{log_msg.id}/{file_name}?hash={hash_val}"
    if getattr(Var, 'SHORTLINK', None):
        try:
            stream_link, download_link = await asyncio.gather(
                asyncio.to_thread(get_shortlink, stream_link), 
                asyncio.to_thread(get_shortlink, download_link)
            )
        except Exception as e:
            logger.error(f"❌ Shortlink generation failed in channel handler: {e}")

    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Stream Now", url=stream_link), 
        InlineKeyboardButton("⬇️ Download", url=download_link)
    ]])

    for attempt in range(3):
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=broadcast.id,
                reply_markup=markup
            )
            
            await log_msg.reply_text(
                text=(
                    "> 🎥 **New Video Upload Detected** 🎥\n\n"
                    f"🏷️ **Channel Name:** `{broadcast.chat.title}`\n"
                    f"🆔 **Channel ID:** `{chat_id}`\n"
                    f"🔗 **Original Link:** `{stream_link}`"
                ),
                quote=True
            )
            logger.info(f"✅ Successfully appended streaming buttons in channel {chat_id}")
            break
            
        except FloodWait as w:
            logger.warning(f"⚠️ FloodWait in channel {chat_id}. Retrying in {w.value}s (Attempt {attempt + 1}/3)")
            await asyncio.sleep(w.value + 1)
            if attempt == 2:
                logger.error(f"❌ FloodWait exhausted for channel {chat_id}. Aborting button attachment.")
                await bot.send_message(
                    chat_id=Var.BIN_CHANNEL, 
                    text=f"> 🚨 **FloodWait Failed after retries**\n\n📡 From Channel: `{broadcast.chat.title}`\n🆔 Channel ID: `{chat_id}`", 
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"❌ Unexpected error editing message in channel {chat_id}: {e}", exc_info=True)
            break
