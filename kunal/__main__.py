import os, sys, glob, asyncio, logging, importlib, traceback, aiohttp

# Create event loop before importing pyrogram to fix Python 3.10+ RuntimeError
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pathlib import Path
from pyrogram import idle
from aiohttp import web
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.text import Text

from .bot import StreamBot
from .vars import Var
from .server import web_server
from kunal.bot.clients import initialize_clients

console = Console()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
for logger in ["aiohttp", "pyrogram", "aiohttp.web"]:
    logging.getLogger(logger).setLevel(logging.ERROR)

files = glob.glob("kunal/bot/plugins/*.py")

async def ping_server():
    while True:
        await asyncio.sleep(Var.PING_INTERVAL)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(Var.URL) as resp:
                    logging.info(f"Pinged server with response: {resp.status}")
        except asyncio.TimeoutError:
            logging.warning("Couldn't connect to the site URL..!")
        except Exception:
            logging.error("Ping failed:", exc_info=True)

async def start_services():
    console.print("\n[bold cyan]🔧 Initializing Telegram Bot...[/bold cyan]")
    await StreamBot.start()
    bot_info = await StreamBot.get_me()
    StreamBot.username = bot_info.username
    
    console.print("[green]✅ Bot initialized successfully![/green]\n[bold cyan]📲 Initializing Clients...[/bold cyan]")
    await initialize_clients()
    
    console.print("[green]✅ Clients initialized![/green]\n[bold cyan]📦 Importing Plugins...[/bold cyan]")
    for name in files:
        plugin_name = Path(name).stem
        spec = importlib.util.spec_from_file_location(f".plugins.{plugin_name}", Path(f"kunal/bot/plugins/{plugin_name}.py"))
        load = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load)
        sys.modules[f"kunal.bot.plugins.{plugin_name}"] = load
        console.print(f"[blue]➤ Imported:[/blue] {plugin_name}")

    if Var.ON_HEROKU:
        console.print("\n[bold magenta]🌐 Starting Keep Alive Service...[/bold magenta]")
        asyncio.create_task(ping_server())

    console.print("\n[bold cyan]🚀 Starting Web Server...[/bold cyan]")
    app = web.AppRunner(await web_server())
    await app.setup()
    bind_address = "0.0.0.0" if Var.ON_HEROKU else Var.BIND_ADDRESS
    await web.TCPSite(app, bind_address, Var.PORT).start()
    console.print("[green]✅ Web server started successfully![/green]\n")

    summary_text = Text()
    summary_text.append("📡 Bot: ", style="bold white").append(f"{bot_info.first_name}\n")
    summary_text.append("🌍 Server IP: ", style="bold white").append(f"{bind_address}:{Var.PORT}\n")
    summary_text.append("👑 Owner: ", style="bold white").append(f"@{Var.OWNER_USERNAME}\n")
    if Var.ON_HEROKU:
        summary_text.append("🔗 App URL: ", style="bold white").append(f"{Var.URL}\n")

    console.print(Panel(summary_text, title="✅ [bold green]Service Started[/bold green]", border_style="cyan", box=box.ROUNDED))

    try:
        await StreamBot.send_message(chat_id=Var.OWNER_ID[0], text='<b>🔄 ʀᴇsᴛᴀʀᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ. sʏsᴛᴇᴍ ɪs ʙᴀᴄᴋ ᴏɴʟɪɴᴇ ✅</b>')
    except Exception as e:
        console.print(f"[red]❌ Failed to send restart message to owner:[/red] {e}")
    
    await idle()

if __name__ == '__main__':
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        console.print("[bold red]🛑 Service Stopped by Keyboard Interrupt[/bold red]")
