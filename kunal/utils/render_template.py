from kunal.vars import Var
from kunal.bot import StreamBot
from kunal.utils.file_properties import get_file_ids
from kunal.server.exceptions import InvalidHash
import urllib.parse
import logging
import aiohttp
import jinja2

KunalCC = """Hello {},

<blockquote><b>📡 Welcome to File to Link BOTS!</b>

➤ Send me any <b>file or media</b>  
➤ Or <b>add me as an admin</b> to your channel to instantly generate permanent download links.

Once received, I’ll auto-attach interactive buttons to the post with the direct URL.

✅ Works with both <b>public</b> and <b>private channels</b>.
</blockquote>
"""


def humanbytes(size):
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

async def render_page(id, secure_hash, src=None):
    file = await StreamBot.get_messages(int(Var.BIN_CHANNEL), int(id))
    file_data = await get_file_ids(StreamBot, int(Var.BIN_CHANNEL), int(id))
    if file_data.unique_id[:6] != secure_hash:
        logging.debug(f"link hash: {secure_hash} - {file_data.unique_id[:6]}")
        logging.debug(f"Invalid hash for message with - ID {id}")
        raise InvalidHash

    src = urllib.parse.urljoin(
        Var.URL,
        f"{id}/{urllib.parse.quote_plus(file_data.file_name)}?hash={secure_hash}",
    )

    tag = file_data.mime_type.split("/")[0].strip()
    file_size = humanbytes(file_data.file_size)
    if tag in ["video", "audio"]:
        template_file = "kunal/template/req.html"
    elif file_data.mime_type == "application/pdf" or file_data.file_name.lower().endswith(".pdf"):
        template_file = "kunal/template/pdf.html"
    else:
        template_file = "kunal/template/dl.html"
        async with aiohttp.ClientSession() as s:
            async with s.get(src) as u:
                file_size = humanbytes(int(u.headers.get("Content-Length")))

    with open(template_file) as f:
        template = jinja2.Template(f.read())

    file_name = file_data.file_name.replace("_", " ")

    return template.render(
        file_name=file_name,
        file_url=src,
        file_size=file_size,
        file_unique_id=file_data.unique_id,
    )

