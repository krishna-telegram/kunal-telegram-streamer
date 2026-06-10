import string
import random
import logging
import base64
import os
import aiohttp
from kunal.vars import Var

logger = logging.getLogger(__name__)

def generate_random_alphanumeric() -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

async def get_shortlink(url: str) -> str:
    if not getattr(Var, 'SHORTLINK', None):
        return url
    try:
        api_url = f"https://{Var.SHORTLINK_URL}/api?api={Var.SHORTLINK_API}&url={url}&alias={generate_random_alphanumeric()}"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    rjson = await response.json()
                    if rjson.get("status") == "success":
                        return rjson.get("shortenedUrl")
    except Exception as e:
        logger.error(f"Shortlink API error: {e}")
    return url

def humanbytes(size: int) -> str:
    if not size: return ""
    power, n = 2**10, 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

async def get_thumbnail_base64(bot, msg) -> str | None:
    try:
        thumb = None
        if getattr(msg, 'photo', None) and msg.photo.thumbs:
            thumb = msg.photo.thumbs[0].file_id
        elif getattr(msg, 'video', None) and msg.video.thumbs:
            thumb = msg.video.thumbs[0].file_id
            
        if thumb:
            file_path = await bot.download_media(thumb)
            if file_path:
                with open(file_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                os.remove(file_path)
                return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.warning(f"Failed to fetch thumb: {e}")
    return None
