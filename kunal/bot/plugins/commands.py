import os
import logging
import httpx
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from kunal.bot import StreamBot
from kunal.vars import Var
from kunal.utils.database import Database
from kunal.utils.render_template import KunalCC

logger = logging.getLogger(__name__)
db = Database(Var.DATABASE_URL, Var.name)

async def download_random_profile_image(retries=3):
    path = "fallback_profile.jpg"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for i in range(retries):
            try:
                res = await client.get("https://picsum.photos/600")
                if res.status_code == 200:
                    with open(path, "wb") as f: f.write(res.content)
                    return path
            except Exception as e:
                logging.error(f"Image download attempt {i+1} failed: {e}")
    return path if os.path.exists(path) else None

async def check_user_sub(bot, user_id):
    if Var.UPDATES_CHANNEL == "None": return True
    try:
        return (await bot.get_chat_member(Var.UPDATES_CHANNEL, user_id)).status != "kicked"
    except UserNotParticipant:
        return "not_joined"
    except Exception as e:
        logging.error(f"Error checking chat member: {e}")
        return "error"

@StreamBot.on_callback_query(filters.regex("check_sub"))
async def check_sub(bot, query):
    sub_status = await check_user_sub(bot, query.from_user.id)
    
    if sub_status == "not_joined":
        return await query.answer("❌ You still haven't joined the channel.", show_alert=True)
    elif sub_status is True:
        await query.message.delete()
        return await bot.send_message(query.message.chat.id, "✅ Subscription verified successfully!\n\nNow send me a file/link.")

@StreamBot.on_message(filters.command("start") & filters.private)
async def start(b, m):
    if not await db.is_user_exist(m.from_user.id):
        await db.add_user(m.from_user.id)
        await b.send_message(Var.NEW_USER_LOG, f"#NewUser\n\n**Name - [{m.from_user.first_name}](tg://user?id={m.from_user.id})**")

    sub_status = await check_user_sub(b, m.from_user.id)
    photo_file = await download_random_profile_image()

    if sub_status == "not_joined":
        caption = f"{m.from_user.mention},\n\n<b><i>⚠️ Please join the updates channel to use this bot.</i></b>\n\n<i>Due to high traffic, access is limited to subscribers only 😊</i>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Updates Channel", url="https://t.me/+Z-Tbu-C9csc0MjVh")]])
        
        if photo_file:
            return await b.send_photo(chat_id=m.chat.id, photo=photo_file, caption=caption, reply_markup=markup)
        return await b.send_message(chat_id=m.chat.id, text=caption, reply_markup=markup)
        
    elif sub_status == "error":
        return await b.send_message(m.chat.id, "<b>⚠️ Something went wrong. <a href='https://telegram.me/TechifySupport'>Click here for support</a></b>", disable_web_page_preview=True)
    elif sub_status is False:
        return await b.send_message(m.chat.id, "❌ Sorry, you are banned from using this bot. Please contact the owner for assistance.", disable_web_page_preview=True)

    # Standard welcome workflow
    caption = KunalCC.format(m.from_user.mention(style="md"))
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/got_nirvana")]])
    
    if photo_file:
        await b.send_photo(chat_id=m.chat.id, photo=photo_file, caption=caption, reply_markup=markup)
    else:
        await b.send_message(chat_id=m.chat.id, text=caption, reply_markup=markup)

@StreamBot.on_message(filters.command('ban') & filters.user(Var.OWNER_ID))
async def do_ban(bot, message):
    args = message.text.split(" ", 2)
    if len(args) < 2:
        return await message.reply('<b>Please add a valid user/channel ID with this command\n\nEx: /ban (user/channel_id) (banning reason[Optional]) \nReal Ex: <code>/ban 1234567899</code>\nWith reason Ex:<code>/ban 1234567899 sending adult links to bot</code>\nTo ban a channel:\n<code>/ban CHANNEL_ID</code>\nEx: <code>/ban -1001234567899</code></b>')
    
    userid, reason = args[1], args[2] if len(args) > 2 else 'no reason provided'
    text = await message.reply("<b>Let me check 👀</b>")
    
    if await db.ban_user(userid):
        await text.edit(
            text=f"<b><code>{userid}</code> has been banned successfully\n\nShould I send an alert to the banned user?</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes ✅", callback_data=f"sendAlert_{userid}_{reason}"),
                 InlineKeyboardButton("No ❌", callback_data=f"noAlert_{userid}")]
            ])
        )
    else:
        await text.edit(f"<b>Control your anger bro...\n<code>{userid}</code> is already banned !!</b>")

@StreamBot.on_message(filters.command('unban') & filters.user(Var.OWNER_ID))
async def do_unban(bot, message):
    args = message.text.split(" ", 1)
    if len(args) < 2:
        return await message.reply('Give me an ID\nEx: <code>/unban 1234567899</code>')
        
    userid = args[1]
    text = await message.reply("<b>Let me check 🥱</b>")
    unban_chk = await db.is_unbanned(userid)
    
    if unban_chk is True:
        await text.edit(
            text=f'<b><code>{userid}</code> is unbanned\nShould I send the happy news alert to the unbanned user?</b>',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes ✅", callback_data=f"sendUnbanAlert_{userid}"),
                 InlineKeyboardButton("No ❌", callback_data=f"NoUnbanAlert_{userid}")]
            ])
        )
    else:
        await text.edit('<b>User is not banned yet.</b>' if unban_chk is False else f"<b>Failed to unban user/channel.\nReason: {unban_chk}</b>")

@StreamBot.on_callback_query()
async def cb_handler(client, query):
    data = query.data
    if data == "close":
        return await query.message.delete()
        
    if data == "start":
        return await query.message.edit_caption(
            caption=KunalCC.format(query.from_user.mention(style="md")),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/got_nirvana")]])
        )

    args = data.split("_")
    cmd, user_id = args[0], int(args[1].replace(' ', ''))
    is_valid_user = len(str(user_id)) == 10

    if cmd == "sendAlert":
        if not is_valid_user:
            return await query.message.edit("<b>⚠️ The process was not completed because the user ID was not valid, or perhaps it was a channel ID.</b>")
        reason = args[2]
        try:
            await client.send_message(user_id, f"<b>🚫 You are banned by [KUNAL](https://t.me/got_nirvana)\nReason: {reason}</b>")
            await query.message.edit(f"<b>✅ Alert sent to <code>{user_id}</code>\nReason: {reason}</b>")
        except Exception as e:
            await query.message.edit(f"<b>❌ Sorry, I got this error: {e}</b>")

    elif cmd == "noAlert":
        await query.message.edit(f"<b>🤫 The ban on <code>{user_id}</code> was executed silently.</b>")

    elif cmd == "sendUnbanAlert":
        if not is_valid_user:
            return await query.message.edit("<b>⚠️ The process was not completed because the user ID was not valid, or perhaps it was a channel ID.</b>")
        try:
            unban_text = "<b>🎉 Hurray... You are unbanned by [KUNAL](https://t.me/got_nirvana)</b>"
            await client.send_message(user_id, unban_text)
            await query.message.edit(f"<b>✅ Unbanned Alert sent to <code>{user_id}</code>\nAlert text: {unban_text}</b>")
        except Exception as e:
            await query.message.edit(f"<b>❌ Sorry, I got this error: {e}</b>")
            
    elif cmd == "NoUnbanAlert":
        await query.message.edit(f"<b>🤫 The unban on <code>{user_id}</code> was executed silently.</b>")
