import re
import asyncio
import logging
from urllib.parse import quote_plus
from pyrogram import filters
from pyrogram.errors import FloodWait, MessageNotModified, MessageIdInvalid
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from kunal.bot import StreamBot
from kunal.vars import Var
from kunal.utils.file_properties import get_name, get_hash, get_media_from_message
from kunal.utils.helpers import get_shortlink

logger = logging.getLogger(__name__)

@StreamBot.on_message(filters.command("addbuttons") & (filters.channel | filters.group), group=-1)
async def add_buttons_handler(bot, message):
    chat_id = message.chat.id
    temp_msgs = [message]
    
    ask_url = await message.reply_text("Send URL(s):\nSingle: `https://t.me/username/123`\nRange: `https://t.me/username/123 to 150`")
    temp_msgs.extend([ask_url, await bot.listen(chat_id)])
    text_input = (temp_msgs[-1].text or "").strip()
    
    if not text_input:
        for msg in temp_msgs:
            try: await msg.delete()
            except: pass
        return await bot.send_message(chat_id, "❌ Invalid input.")
        
    targets = []
    range_match = re.match(r"https://t\.me/(?:c/(\d+)|([\w_]+))/(\d+)\s*to\s*(\d+)", text_input)
    single_match = re.match(r"https://t\.me/(?:c/(\d+)|([\w_]+))/(\d+)", text_input)

    if range_match:
        target_chat = int(f"-100{range_match.group(1)}") if range_match.group(1) else range_match.group(2)
        for i in range(int(range_match.group(3)), int(range_match.group(4)) + 1):
            targets.append((target_chat, i))
    elif single_match:
        target_chat = int(f"-100{single_match.group(1)}") if single_match.group(1) else single_match.group(2)
        targets.append((target_chat, int(single_match.group(3))))
    else:
        for msg in temp_msgs:
            try: await msg.delete()
            except: pass
        return await bot.send_message(chat_id, "❌ Invalid format.")

    ask_action = await bot.send_message(chat_id, "Reply with:\n`replace` to overwrite\n`edit` to append")
    temp_msgs.extend([ask_action, await bot.listen(chat_id)])
    action = (temp_msgs[-1].text or "").lower().strip()

    if action not in ["replace", "edit"]:
        for msg in temp_msgs:
            try: await msg.delete()
            except: pass
        return await bot.send_message(chat_id, "❌ Invalid choice.")

    ask_sleep = await bot.send_message(chat_id, "Enter delay (e.g., `2`):")
    temp_msgs.extend([ask_sleep, await bot.listen(chat_id)])
    sleep_time = max(1, int(temp_msgs[-1].text.strip() if temp_msgs[-1].text.strip().isdigit() else 2))

    for msg in temp_msgs:
        try: await msg.delete()
        except: pass

    status_msg = await bot.send_message(chat_id, f"⏳ Updating {len(targets)} posts...")
    success_count = 0

    for target_chat, post_id in targets:
        try:
            original_message = await bot.get_messages(chat_id=target_chat, message_ids=post_id)
            if not original_message or original_message.empty or not get_media_from_message(original_message):
                continue

            try:
                log_msg = await original_message.copy(chat_id=Var.BIN_CHANNEL, reply_markup=None)
            except Exception:
                media = get_media_from_message(original_message)
                if getattr(original_message, "video", None):
                    log_msg = await bot.send_video(Var.BIN_CHANNEL, media.file_id, caption=original_message.caption or "")
                elif getattr(original_message, "photo", None):
                    log_msg = await bot.send_photo(Var.BIN_CHANNEL, media.file_id, caption=original_message.caption or "")
                else:
                    log_msg = await bot.send_document(Var.BIN_CHANNEL, media.file_id, caption=original_message.caption or "")
            
            name_quoted, hash_val = quote_plus(get_name(log_msg)), get_hash(log_msg)
            stream_link, download_link = await asyncio.gather(
                get_shortlink(f"{Var.URL}watch/{log_msg.id}/{name_quoted}?hash={hash_val}"),
                get_shortlink(f"{Var.URL}{log_msg.id}/{name_quoted}?hash={hash_val}")
            )

            new_btns = [InlineKeyboardButton("🎬 Stream Now", url=stream_link), InlineKeyboardButton("⬇️ Download", url=download_link)]
            markup = [new_btns] if action == "replace" else (original_message.reply_markup.inline_keyboard if original_message.reply_markup else []) + [new_btns]
            
            if original_message.reply_markup:
                try: await bot.edit_message_reply_markup(original_message.chat.id, post_id, reply_markup=None)
                except MessageNotModified: pass
            
            try:
                await bot.edit_message_reply_markup(original_message.chat.id, post_id, InlineKeyboardMarkup(markup))
                success_count += 1
                logger.info(f"🔘 [BULK ADD] Added buttons to {target_chat} / {post_id}")
            except MessageNotModified:
                success_count += 1
                logger.info(f"🔘 [BULK ADD SKIP] Buttons already matched on {target_chat} / {post_id}")
            except FloodWait as e:
                logger.warning(f"⚠️ [FLOOD WAIT] Bulk Add sleeping for {e.value}s")
                await asyncio.sleep(e.value)
                await bot.edit_message_reply_markup(original_message.chat.id, post_id, InlineKeyboardMarkup(markup))
                success_count += 1
                logger.info(f"🔘 [BULK ADD] Added buttons to {target_chat} / {post_id} after delay")
            
            await asyncio.sleep(sleep_time)
        except Exception as e:
            logger.error(f"❌ [BULK ADD FAILED] Error on post {target_chat}/{post_id}: {e}")
            
    await status_msg.edit(f"✅ Updated {success_count}/{len(targets)} posts!")


@StreamBot.on_message(filters.command("removebuttons") & (filters.channel | filters.group), group=-1)
async def remove_buttons_handler(bot, message):
    chat_id = message.chat.id
    temp_msgs = [message]
    
    try:
        ask_url = await message.reply_text("Send link or range:\n`https://t.me/channel/100`\n`https://t.me/channel/100 to 120`")
        temp_msgs.extend([ask_url, await bot.listen(chat_id)])
        text = (temp_msgs[-1].text or "").strip()
        
        match = re.search(r"(?:https://t\.me/)?(?:c/(\d+)|([\w_]+))/(\d+)(?:\s+to\s+(\d+))?", text)
        if not match: raise ValueError("Invalid format")

        target_chat = int(f"-100{match.group(1)}") if match.group(1) else match.group(2)
        start_id, end_id = int(match.group(3)), int(match.group(4) or match.group(3))

        ask_sleep = await bot.send_message(chat_id, "Enter delay (seconds):")
        temp_msgs.extend([ask_sleep, await bot.listen(chat_id)])
        sleep_time = int(temp_msgs[-1].text.strip() if temp_msgs[-1].text.strip().isdigit() else 2)
    except Exception as e:
        for msg in temp_msgs:
            try: await msg.delete()
            except: pass
        return await bot.send_message(chat_id, f"❌ Error: {e}")

    for msg in temp_msgs:
        try: await msg.delete()
        except: pass

    status = await bot.send_message(chat_id, f"⏳ Removing buttons {start_id}-{end_id}")
    success, failed = 0, 0

    for post_id in range(start_id, end_id + 1):
        try:
            msg = await bot.get_messages(target_chat, post_id)
            if not msg:
                failed += 1; continue
            if not msg.reply_markup:
                success += 1; continue
                
            await bot.edit_message_reply_markup(target_chat, post_id, None)
            success += 1
            logger.info(f"🗑️ [BULK REMOVE] Removed buttons from {target_chat} / {post_id}")
        except (MessageNotModified, MessageIdInvalid):
            success += 1
            logger.info(f"🗑️ [BULK REMOVE SKIP] Ignored {target_chat} / {post_id}")
        except FloodWait as e:
            logger.warning(f"⚠️ [FLOOD WAIT] Bulk Remove sleeping for {e.value}s")
            await asyncio.sleep(e.value)
            try:
                await bot.edit_message_reply_markup(target_chat, post_id, None)
                success += 1
                logger.info(f"🗑️ [BULK REMOVE] Removed buttons from {target_chat} / {post_id} after delay")
            except Exception as e:
                failed += 1
                logger.error(f"❌ [BULK REMOVE FAILED] Error after flood wait on {target_chat}/{post_id}: {e}")
        except Exception as e:
            failed += 1
            logger.error(f"❌ [BULK REMOVE FAILED] Unexpected error on {target_chat}/{post_id}: {e}")
        await asyncio.sleep(sleep_time)

    await status.edit_text(f"✅ Done\nSuccess: {success}\nFailed: {failed}")
