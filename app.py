import requests
import os
import asyncio
import threading
import time
import psutil
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
BASE_URL = "https://giga-seven.vercel.app/api"

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8000))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

OWNER_ID = 6804892450
LOG_CHANNEL_ID = -1003453546878

MONGO_URI = "mongodb+srv://sk5400552:shjjkytdcghhudd@cluster0g.kbllv.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0g"

FORCE_CHAT_IDS = [-1003559174618, -1003317410802]

JOIN_LINKS = [
    "https://t.me/+BkMdZGT0ryBkMThl",
    "https://t.me/+HidgJvH0BktiZmI9"
]

BOT_START_TIME = datetime.now()
LAST_SAMPLE = {"cpu": 0.0, "ram": 0.0, "ram_used": 0, "ram_total": 0}
HIGH_CPU_COUNT = 0

# ---------------- MongoDB ----------------

mongo_client = MongoClient(MONGO_URI)
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

# ---------------- Background Samplers ----------------

def resource_sampler():
    global HIGH_CPU_COUNT
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()

            LAST_SAMPLE["cpu"] = cpu
            LAST_SAMPLE["ram"] = mem.percent
            LAST_SAMPLE["ram_used"] = mem.used // (1024 * 1024)
            LAST_SAMPLE["ram_total"] = mem.total // (1024 * 1024)

            if cpu > 80:
                HIGH_CPU_COUNT += 1
            else:
                HIGH_CPU_COUNT = 0

            if HIGH_CPU_COUNT >= 3:
                text = f"🚨 High CPU Alert\nCPU: {cpu:.1f}%"
                logs_col.insert_one({"text": text, "time": datetime.now()})
                try:
                    asyncio.run_coroutine_threadsafe(
                        tg_app.bot.send_message(LOG_CHANNEL_ID, text),
                        main_loop
                    )
                except:
                    pass
                HIGH_CPU_COUNT = 0

        except:
            pass

        time.sleep(5)

threading.Thread(target=resource_sampler, daemon=True).start()

# ---------------- Helpers ----------------

async def log_event(text: str):
    logs_col.insert_one({"text": text, "time": datetime.now()})
    try:
        await tg_app.bot.send_message(LOG_CHANNEL_ID, text)
    except:
        pass


def save_user(user):
    users_col.update_one(
        {"user_id": user.id},
        {"$setOnInsert": {
            "username": user.username,
            "first_name": user.first_name,
            "time": datetime.now()
        }},
        upsert=True
    )


def inc_lookup():
    today = datetime.now().strftime("%Y-%m-%d")
    stats_col.update_one(
        {"date": today},
        {"$inc": {"lookups": 1}},
        upsert=True
    )


def is_owner(uid: int):
    return uid == OWNER_ID


def format_uptime():
    delta: timedelta = datetime.now() - BOT_START_TIME
    d = delta.days
    h, rem = divmod(delta.seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{d}d {h}h {m}m {s}s"

# ---------------- Forced Join Logic ----------------

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
    text = (
        "🚫 *Access Denied*\n\n"
        "You must join all channels to use this bot.\n\n"
        "After joining both channels, press *I Joined*."
    )

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=join_keyboard())
    else:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=join_keyboard())


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

    await log_event(
        f"👤 New Start\nID: {user.id}\nName: {user.first_name}\nUsername: @{user.username}"
    )

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
    r = requests.get(url, timeout=20)
    data = r.json()

    if not data.get("success"):
        await update.message.reply_text(f"⚠️ API Error for {mobile}")
        return

    results = data.get("result", [])
    if not results:
        await update.message.reply_text(f"❌ No data found for {mobile}")
        return

    lines = ["📱 Mobile Lookup Result", f"🔍 Searched Number: {mobile}", "=" * 50]

    for i, info in enumerate(results, 1):
        lines += [
            f"\n📌 Record {i}",
            f"Name: {info.get('name','N/A')}",
            f"Mobile: {info.get('mobile','N/A')}",
            "-" * 40
        ]

    filename = f"lookup_{mobile}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(filename, "rb") as f:
        await update.message.reply_document(f, filename=filename)

    os.remove(filename)


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

# -------- Utility Commands --------

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = time.time()
    msg = await update.message.reply_text("🏓 Pinging...")
    latency = (time.time() - start) * 1000

    s = LAST_SAMPLE
    text = (
        "🏓 Pong!\n\n"
        f"⏱ Latency: {latency:.1f} ms\n"
        f"🕒 Uptime: {format_uptime()}\n"
        f"🧠 CPU: {s['cpu']:.1f}%\n"
        f"💾 RAM: {s['ram']:.1f}%\n"
        f"📦 Memory: {s['ram_used']}MB / {s['ram_total']}MB"
    )

    await msg.edit_text(text)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")

    total_users = users_col.count_documents({})
    today_users = users_col.count_documents({
        "time": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}
    })

    s = stats_col.find_one({"date": today}) or {"lookups": 0}

    text = (
        "📊 Bot Stats\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🆕 Users Today: {today_users}\n"
        f"🔍 Lookups Today: {s.get('lookups', 0)}"
    )

    await update.message.reply_text(text)

# ---------------- Register Handlers ----------------

tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("num", getnumber))
tg_app.add_handler(CommandHandler("ping", ping))
tg_app.add_handler(CommandHandler("stats", stats))
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
    await tg_app.bot.set_webhook(WEBHOOK_URL)

    await log_event("🤖 Bot Restarted / Started")

    print("✅ Webhook set:", WEBHOOK_URL)

asyncio.run_coroutine_threadsafe(startup(), main_loop)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
