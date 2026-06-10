import re
import time
import math
import logging
import secrets
import mimetypes
from aiohttp import web
from aiohttp.http_exceptions import BadStatusLine
from kunal.bot import multi_clients, work_loads, StreamBot
from kunal.server.exceptions import FIleNotFound, InvalidHash
from kunal import StartTime, __version__
from ..utils.custom_dl import ByteStreamer
from kunal.utils.render_template import render_page
from kunal.vars import Var

routes = web.RouteTableDef()

def get_readable_time(seconds: int) -> str:
    count = 0
    readable_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", " days"]
    while count < 4:
        count += 1
        if count < 3:
            remainder, result = divmod(seconds, 60)
        else:
            remainder, result = divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        readable_time += time_list.pop() + ", "
    time_list.reverse()
    readable_time += ": ".join(time_list)
    return readable_time

@routes.get("/", allow_head=True)
async def root_route_handler(_):
    return web.json_response(
        {
            "server_status": "running",
            "uptime": get_readable_time(time.time() - StartTime),
            "telegram_bot": "@" + StreamBot.username,
            "connected_bots": len(multi_clients),
            "loads": dict(
                ("bot" + str(c + 1), l)
                for c, (_, l) in enumerate(
                    sorted(work_loads.items(), key=lambda x: x[1], reverse=True)
                )
            ),
            "version": __version__,
        }
    )


@routes.get(r"/watch/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return web.Response(text=await render_page(id, secure_hash), content_type='text/html')
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        return web.Response(status=400, text="Bad Request or Connection Reset")
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))

@routes.get(r"/{path:\S+}", allow_head=True)
async def stream_handler(request: web.Request):
    try:
        path = request.match_info["path"]
        match = re.search(r"^([a-zA-Z0-9_-]{6})(\d+)$", path)
        if match:
            secure_hash = match.group(1)
            id = int(match.group(2))
        else:
            id = int(re.search(r"(\d+)(?:\/\S+)?", path).group(1))
            secure_hash = request.rel_url.query.get("hash")
        return await media_streamer(request, id, secure_hash)
    except InvalidHash as e:
        raise web.HTTPForbidden(text=e.message)
    except FIleNotFound as e:
        raise web.HTTPNotFound(text=e.message)
    except (AttributeError, BadStatusLine, ConnectionResetError):
        pass
    except Exception as e:
        logging.critical(e.with_traceback(None))
        raise web.HTTPInternalServerError(text=str(e))

class_cache = {}

async def media_streamer(request: web.Request, id: int, secure_hash: str):
    range_header = request.headers.get("Range", 0)
    
    index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[index]

    if faster_client in class_cache:
        tg_connect = class_cache[faster_client]
    else:
        tg_connect = ByteStreamer(faster_client)
        class_cache[faster_client] = tg_connect

    file_id = await tg_connect.get_file_properties(id)
    
    if file_id.unique_id[:6] != secure_hash:
        raise InvalidHash
    
    file_size = file_id.file_size
    file_name = file_id.file_name or "Unknown_Media"

    # =========================================================================
    # PRODUCTION LEVEL METRIC LOGGING (Captures initial plays & seeking tracks)
    # =========================================================================
    if not range_header or range_header == "bytes=0-":
        playback_action = "▶️ PLAYING"
    else:
        try:
            start_byte = int(range_header.replace("bytes=", "").split("-")[0])
            ratio = start_byte / file_size if file_size > 0 else 0
            playback_action = f"⏩ SEEK/RESUME ({round(ratio * 100)}%)"
        except Exception:
            playback_action = "▶️ PLAYING"

    # Only output logs during structural client connection initializations or seek triggers
    if not range_header or (range_header and "0-" in range_header) or "SEEK" in playback_action:
        viewer_ip = request.headers.get('X-Forwarded-For', request.remote)
        if viewer_ip and ',' in viewer_ip:
            viewer_ip = viewer_ip.split(',')[0].strip()

        size_mb = round(file_size / (1024 * 1024), 2)

        user_agent = request.headers.get('User-Agent', 'Unknown')
        if any(mobile in user_agent for mobile in ["Mobile", "Android", "iPhone", "iPad"]):
            device = "📱 Mobile"
        else:
            device = "💻 Desktop"

        referer = request.headers.get('Referer', 'Direct Link')
        if "telegram" in referer.lower() or "t.me" in referer.lower():
            source = "Telegram"
        else:
            source = referer.split('//')[-1].split('/')[0] if '//' in referer else referer

        current_load = work_loads.get(index, 0)

        logging.info(
            f"{playback_action}: {file_name} ({size_mb} MB) | "
            f"IP: {viewer_ip} | "
            f"Device: {device} | "
            f"Source: {source} | "
            f"Bot ID: {index} (Active Loads: {current_load})"
        )
    # =========================================================================

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        until_bytes = (request.http_range.stop or file_size) - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        return web.Response(
            status=416,
            body="416: Range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)

    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    part_count = math.ceil(until_bytes / chunk_size) - math.floor(offset / chunk_size)
    body = tg_connect.yield_file(
        file_id, index, offset, first_part_cut, last_part_cut, part_count, chunk_size
    )

    mime_type = file_id.mime_type
    disposition = "attachment"

    if mime_type:
        if not file_name or file_name == "Unknown_Media":
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name and file_name != "Unknown_Media":
            mime_type = mimetypes.guess_type(file_name)
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"

    return web.Response(
        status=206 if range_header else 200,
        body=body,
        headers={
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        },
    )
