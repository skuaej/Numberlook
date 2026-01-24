import requests
import os
import asyncio
import threading
import time
import psutil
import glob
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler
)
from pymongo import MongoClient

# ---------------- CONFIG ----------------

API_KEY = "jakiez"
BASE_URL = "https://usesirosint.vercel.app/api/numinfo"

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))
WEBHOOK_PATH = "/webhook"

OWNER_ID = 6804892450
LOG_CHANNEL_ID = -1003453546878

MONGO_URI = os.getenv("MONGO_URI")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN is not set")

if not WEBHOOK_URL:
    raise RuntimeError("❌ WEBHOOK_URL is not set")

if not MONGO_URI:
    raise RuntimeError("❌ MONGO_URI is not set")

FORCE_CHAT_IDS = [-1003559174618, -1003317410802]

JOIN_LINKS = [
    "https://t.me/+BkMdZGT0ryBkMThl",
    "https://t.me/+HidgJvH0BktiZmI9"
]

BOT_START_TIME = datetime.now()
LAST_SAMPLE = {"cpu": 0.0, "ram": 0.0, "ram_used": 0, "ram_total": 0}
HIGH_RAM_COUNT = 0

# ---------------- MongoDB ----------------

mongo_client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000
)

db = mongo_client["eyelookup_bot"]
users_col = db["users"]
logs_col = db["logs"]
stats_col = db["stats"]

# ---------------- INIT ----------------

flask_app = Flask(__name__)
tg_app = ApplicationBuilder().token(BOT_TOKEN).build()

main_loop = asyncio.new_event_loop()

def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_loop, args=(main_loop,), daemon=True).start()

# ---------------- Helpers ----------------

def format_uptime():
    delta: timedelta = datetime.now() - BOT_START_TIME
    d = delta.days
    h, rem = divmod(delta.seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{d}d {h}h {m}m {s}s"


def get_disk_usage():
    try:
        usage = psutil.disk_usage("/")
        used = usage.used // (1024 * 1024)
        total = usage.total // (1024 * 1024)
        percent = usage.percent
        return used, total, percent
    except:
        return 0, 0, 0


def cleanup_temp_files():
    deleted = 0
    for f in glob.glob("lookup_*.txt"):
        try:
            os.remove(f)
            deleted += 1
        except:
            pass
    return deleted


async def log_event(text: str):
    try:
        logs_col.insert_one({"text": text, "time": datetime.now()})
    except:
        pass

    try:
        await tg_app.bot.send_message(LOG_CHANNEL_ID, text)
    except:
        pass


def save_user(user):
    try:
        users_col.update_one(
            {"user_id": user.id},
            {"$setOnInsert": {
                "username": user.username,
                "first_name": user.first_name,
                "time": datetime.now()
            }},
            upsert=True
        )
    except:
        pass


def inc_lookup():
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        stats_col.update_one(
            {"date": today},
            {"$inc": {"lookups": 1}},
            upsert=True
        )
    except:
        pass

# ---------------- Forced Join ----------------

async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    for chat_id in FORCE_CHAT_IDS:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            return False
    return True


def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Join Channel 1", url=JOIN_LINKS[0])],
        [InlineKeyboardButton("🔗 Join Channel 2", url=JOIN_LINKS[1])],
        [InlineKeyboardButton("✅ I Joined", callback_data="check_join")]
    ])


async def force_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚫 You must join both channels to use this bot.",
        reply_markup=join_keyboard()
    )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await is_user_joined(q.from_user.id, context):
        await q.message.edit_text("✅ Verified!\n\nUse:\n/num 8797879802")
    else:
        await q.answer("❌ Join both channels & try again.", show_alert=True)

# ---------------- Commands ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    await log_event(f"👤 New Start\nID: {user.id}\nName: {user.first_name}")

    if not await is_user_joined(user.id, context):
        await force_join_message(update, context)
        return

    await update.message.reply_text("👋 Welcome!\n\nUse:\n/num 8797879802")


async def lookup_one(update: Update, context: ContextTypes.DEFAULT_TYPE, mobile: str):
    inc_lookup()

    if not mobile.isdigit() or not (8 <= len(mobile) <= 13):
        await update.message.reply_text(f"❌ Invalid number: {mobile}")
        return

    url = f"{BASE_URL}?key={API_KEY}&num={mobile}"

    try:
        r = requests.get(url, timeout=20)
        data = r.json()
    except Exception as e:
        await update.message.reply_text("⚠️ API not responding or invalid JSON.")
        return

    # --- FLEXIBLE RESPONSE HANDLING ---
    success = data.get("success", True)
    results = data.get("result") or data.get("data") or []

    if not success or not results:
        await update.message.reply_text(f"⚠️ API Error or no data for {mobile}")
        return

    lines = [
        "📱 Mobile Lookup Result",
        f"🔍 Searched Number: {mobile}",
        f"🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 50
    ]

    for i, info in enumerate(results, 1):
        lines += [
            f"\n📌 Record {i}",
            f"Name        : {info.get('name','N/A')}",
            f"Father Name: {info.get('father_name','N/A')}",
            f"Mobile      : {info.get('mobile','N/A')}",
            f"Alt Mobile  : {info.get('alt_mobile','N/A')}",
            f"Circle      : {info.get('circle','N/A')}",
            f"Email       : {info.get('email','N/A')}",
            f"Address     : {info.get('address','N/A')}",
            "-" * 50
        ]

    filename = f"lookup_{mobile}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(filename, "rb") as f:
        file_msg = await update.message.reply_document(
            document=f,
            filename=filename,
            caption="📄 This is the result for your request"
        )

    warn_msg = await update.message.reply_text(
        "⚠️ Save or forward this file.\nThis message will be deleted in 60 seconds."
    )

    await asyncio.sleep(60)

    try:
        await context.bot.delete_message(update.effective_chat.id, file_msg.message_id)
        await context.bot.delete_message(update.effective_chat.id, warn_msg.message_id)
    except:
        pass

    try:
        os.remove(filename)
    except:
        pass


async def do_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE, mobiles: list):
    if not await is_user_joined(update.effective_user.id, context):
        await force_join_message(update, context)
        return

    for m in mobiles:
        await lookup_one(update, context, m)


async def getnumber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage:\n/num 8797879802")
        return
    await do_lookup(update, context, context.args)

# ---------------- Register Handlers ----------------

tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("num", getnumber))
tg_app.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))

# ---------------- Webhook ----------------

@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, tg_app.bot)

    asyncio.run_coroutine_threadsafe(
        tg_app.process_update(update),
        main_loop
    )

    return "ok"

# ---------------- Startup ----------------

async def startup():
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.bot.initialize()

    await tg_app.bot.set_webhook(WEBHOOK_URL)

    await log_event("🤖 Bot Started / Restarted")

    print("✅ Webhook set:", WEBHOOK_URL)

asyncio.run_coroutine_threadsafe(startup(), main_loop)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
