import os
import asyncio
import time
import psutil
import glob
from datetime import datetime, timedelta

import requests
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# ───────── CONFIG ─────────

API_KEY = "jakiez"
BASE_URL = "https://usesirosint.vercel.app/api/numinfo"

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

PORT = int(os.getenv("PORT", 8000))
WEBHOOK_URL = "https://numloook.herokuapp.com/webhook"

OWNER_ID = 6804892450
LOG_CHANNEL_ID = -1003453546878

FORCE_CHAT_IDS = [-1003559174618, -1003317410802]

JOIN_LINKS = [
    "https://t.me/+BkMdZGT0ryBkMThl",
    "https://t.me/+HidgJvH0BktiZmI9"
]

if not BOT_TOKEN or not MONGO_URI:
    raise RuntimeError("Missing ENV variables")

BOT_START_TIME = datetime.now()
LAST_SAMPLE = {"ram": 0, "ram_used": 0, "ram_total": 0}

# ───────── DATABASE ─────────

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo["eyelookup_bot"]
users_col = db["users"]
logs_col = db["logs"]
stats_col = db["stats"]

# ───────── HELPERS ─────────

def format_uptime():
    d = datetime.now() - BOT_START_TIME
    h, r = divmod(d.seconds, 3600)
    m, s = divmod(r, 60)
    return f"{d.days}d {h}h {m}m {s}s"


async def log_event(app, text):
    try:
        logs_col.insert_one({"text": text, "time": datetime.now()})
        await app.bot.send_message(LOG_CHANNEL_ID, text)
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

# ───────── FORCE JOIN ─────────

async def is_user_joined(user_id, context):
    for chat_id in FORCE_CHAT_IDS:
        try:
            m = await context.bot.get_chat_member(chat_id, user_id)
            if m.status in ("left", "kicked"):
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


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await is_user_joined(q.from_user.id, context):
        await q.message.edit_text("✅ Verified!\n\nUse:\n/num 8797879802")
    else:
        await q.answer("❌ Join both channels", show_alert=True)

# ───────── COMMANDS ─────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    if not await is_user_joined(user.id, context):
        await update.message.reply_text(
            "🚫 Join both channels first",
            reply_markup=join_keyboard()
        )
        return

    await update.message.reply_text("👋 Welcome!\n\nUse:\n/num 8797879802")


async def getnumber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /num 8797879802")
        return

    if not await is_user_joined(update.effective_user.id, context):
        await update.message.reply_text(
            "🚫 Join both channels",
            reply_markup=join_keyboard()
        )
        return

    for mobile in context.args:
        await lookup_one(update, context, mobile)


async def lookup_one(update, context, mobile):
    inc_lookup()

    if not mobile.isdigit():
        await update.message.reply_text("❌ Invalid number")
        return

    url = f"{BASE_URL}?key={API_KEY}&num={mobile}"

    try:
        r = requests.get(url, timeout=20).json()
    except:
        await update.message.reply_text("⚠️ API error")
        return

    if not r.get("success"):
        await update.message.reply_text("❌ No data found")
        return

    results = r.get("result", [])
    lines = [
        f"📱 Mobile: {mobile}",
        f"📊 Records: {len(results)}",
        "-" * 40
    ]

    for i, x in enumerate(results, 1):
        lines += [
            f"\n📌 Record {i}",
            f"Name: {x.get('name')}",
            f"Father: {x.get('father_name')}",
            f"Alt: {x.get('alt_mobile')}",
            f"Circle: {x.get('circle')}",
            f"Email: {x.get('email')}",
            f"Address: {x.get('address')}",
        ]

    filename = f"lookup_{mobile}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(filename, "rb") as f:
        msg = await update.message.reply_document(f)

    await asyncio.sleep(60)

    try:
        await msg.delete()
        os.remove(filename)
    except:
        pass


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mem = psutil.virtual_memory()
    await update.message.reply_text(
        f"🏓 Pong\n"
        f"⏱ Uptime: {format_uptime()}\n"
        f"💾 RAM: {mem.percent}%"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    users = users_col.count_documents({})
    s = stats_col.find_one({"date": today}) or {"lookups": 0}

    await update.message.reply_text(
        f"📊 Stats\n"
        f"👥 Users: {users}\n"
        f"🔍 Lookups Today: {s['lookups']}"
    )

# ───────── MAIN ─────────

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("num", getnumber))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))

    print("🚀 Starting webhook")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
