import os, time, string, random, asyncio, aiofiles, datetime
from kunal.utils.broadcast_helper import send_msg
from kunal.utils.database import Database
from kunal.bot import StreamBot
from kunal.vars import Var
from pyrogram import filters, Client
from pyrogram.types import Message

db = Database(Var.DATABASE_URL, Var.name)
Broadcast_IDs = {}

@StreamBot.on_message(filters.command("users") & filters.private & filters.user(Var.OWNER_ID))
async def sts(c: Client, m: Message):
    total_users = await db.total_users_count()
    await m.reply_text(text=f"Total Users in DB: {total_users}", quote=True)

@StreamBot.on_message(filters.command("broadcast") & filters.private & filters.user(list(Var.OWNER_ID)))
async def broadcast_(c, m):
    if not m.reply_to_message:
        return await m.reply_text("<b>Pʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ.</b>")

    out = await m.reply_text("Broadcast initiated! You will be notified with a log file when all users are notified.")
    
    while True:
        broadcast_id = ''.join(random.choices(string.ascii_letters, k=3))
        if broadcast_id not in Broadcast_IDs: break

    total_users = await db.total_users_count()
    done, failed, success, start_time = 0, 0, 0, time.time()
    Broadcast_IDs[broadcast_id] = {"total": total_users, "current": done, "failed": failed, "success": success}
    
    log_file_path = f"broadcast_{broadcast_id}.txt"
    all_users = await db.get_all_users()

    try:
        async with aiofiles.open(log_file_path, 'w') as log_file:
            async for user in all_users:
                if broadcast_id not in Broadcast_IDs: break
                
                user_id = int(user['id'])
                sts, msg = await send_msg(user_id=user_id, message=m.reply_to_message)
                
                if msg: 
                    await log_file.write(msg)
                
                if sts == 200: 
                    success += 1
                else: 
                    failed += 1
                    if sts == 400: await db.delete_user(user_id)
                
                done += 1
                Broadcast_IDs[broadcast_id].update({"current": done, "failed": failed, "success": success})
    finally:
        Broadcast_IDs.pop(broadcast_id, None)

    completed_in = datetime.timedelta(seconds=int(time.time() - start_time))
    try: await out.delete()
    except Exception: pass

    text = f"broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done}, {success} success and {failed} failed."
    
    if failed == 0 or not os.path.exists(log_file_path):
        await m.reply_text(text=text, quote=True)
    else:
        await m.reply_document(document=log_file_path, caption=text, quote=True)
        
    if os.path.exists(log_file_path): 
        os.remove(log_file_path)
