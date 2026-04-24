from functools import partial
from asyncio import get_running_loop
from shutil import rmtree
from pathlib import Path
import logging
import os

from dotenv import load_dotenv
from telethon import TelegramClient, events

from utils import download_files, add_to_zip

load_dotenv()

# --- ENV ---
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

CONC_MAX = int(os.environ.get("CONC_MAX", 3))

STORAGE = Path("./files")
STORAGE.mkdir(exist_ok=True)

# --- LOGGING ---
logging.basicConfig(
    format='[%(levelname)s/%(asctime)s] %(name)s: %(message)s',
    level=logging.INFO
)

# user state
tasks: dict[int, list[int]] = {}

# --- CLIENT ---
bot = TelegramClient(
    "quick-zip-bot",
    API_ID,
    API_HASH
).start(bot_token=BOT_TOKEN)


# --- HANDLERS ---

@bot.on(events.NewMessage(pattern=r"^/add$"))
async def add_handler(event):
    tasks[event.sender_id] = []
    await event.respond("OK, send me files now.")


@bot.on(events.NewMessage(func=lambda e: e.sender_id in tasks and e.file))
async def collect_files(event):
    tasks[event.sender_id].append(event.id)


@bot.on(events.NewMessage(pattern=r"^/zip (\w+)$"))
async def zip_handler(event):
    user_id = event.sender_id

    if user_id not in tasks:
        await event.respond("Use /add first.")
        return

    if not tasks[user_id]:
        await event.respond("No files received.")
        return

    messages = await bot.get_messages(user_id, ids=tasks[user_id])

    total_size = sum((m.file.size or 0) for m in messages if m.file)

    if total_size > 2 * 1024 * 1024 * 1024:
        await event.respond("Max size is 2GB.")
        return

    root = STORAGE / str(user_id)
    root.mkdir(parents=True, exist_ok=True)

    zip_name = root / f"{event.pattern_match.group(1)}.zip"

    async for file in download_files(messages, CONC_MAX, root):
        await get_running_loop().run_in_executor(
            None,
            partial(add_to_zip, zip_name, file)
        )

    await event.respond("Done!", file=str(zip_name))

    await get_running_loop().run_in_executor(
        None,
        rmtree,
        root
    )

    tasks.pop(user_id, None)


@bot.on(events.NewMessage(pattern=r"^/cancel$"))
async def cancel_handler(event):
    tasks.pop(event.sender_id, None)
    await event.respond("Canceled.")


# --- START ---
if __name__ == "__main__":
    print("Bot is running...")
    bot.run_until_disconnected()