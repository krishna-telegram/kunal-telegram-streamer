import asyncio
import logging
from ..vars import Var
from pyrogram import Client
from kunal.utils.config_parser import TokenParser
from kunal.bot import multi_clients, work_loads, StreamBot

async def initialize_clients():
    multi_clients[0], work_loads[0] = StreamBot, 0
    all_tokens = TokenParser().parse_from_env()
    if not all_tokens:
        return print("No additional clients found, using default client")

    async def start_client(i, token):
        try:
            print(f"Starting - Client {i}")
            if i == len(all_tokens):
                await asyncio.sleep(2)
                print("This will take some time, please wait...")
            
            client = await Client(
                name=str(i), api_id=Var.API_ID, api_hash=Var.API_HASH,
                bot_token=token, sleep_threshold=Var.SLEEP_THRESHOLD,
                no_updates=True, in_memory=True
            ).start()
            work_loads[i] = 0
            return i, client
        except Exception:
            logging.error(f"Failed starting Client - {i}", exc_info=True)

    results = await asyncio.gather(*(start_client(i, t) for i, t in all_tokens.items()))
    multi_clients.update({k: v for k, v in results if v})
    
    if len(multi_clients) > 1:
        Var.MULTI_CLIENT = True
        print("Multi-Client Mode Enabled")
    else:
        print("No additional clients were initialized, using default client")
