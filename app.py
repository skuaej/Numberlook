import os
import asyncio
from datetime import datetime

import requests
import psutil
from pymongo import MongoClient
from flask import Flask, request

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# ───────── CONFIG ─────────

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
APP_URL = os.getenv("APP_URL")  # https://numloook.herokuapp.com
PORT = int(os.environ.get("PORT", 5000))

WEBHOOK_PATH = "webhook"

API_KEY = "jakiez"
BASE_URL = "https://usesirosint.vercel.app/api/numinfo"

OWNER_ID = 6804892450
LOG_CHANNEL_ID = -1003453546878

FORCE_CHAT_IDS = [-1003559174618, -1003317410802]
JOIN_LINKS = [
    "https://t.me/+BkMdZGT0ryBkMThl",
    "https://t.me/+HidgJvH0BktiZmI9"
]

if not BOT_TOKEN or not MONGO_URI or not APP_URL:
    raise RuntimeError("Missing ENV variables")

BOT_START = datetime.now()

# ───────── DATABASE ─────────

mongo = MongoClient(MONGO_URI)
db = mongo["eyelookup_bot"]
users_col = db["users"]
stats_col = db["stats"]

# ───────── HELPERS ─────────

def uptime():
    d = datetime.now() - BOT_START
    h, r = divmod(d.seconds, 3600)
    m, s = divmod(r, 60)
    return f"{d.days}d {h}h {m}m {s}s"

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

async def is_joined(user_id, context):
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

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await is_joined(q.from_user.id, context):
        await q.message.edit_text("✅ Verified!\n\nUse:\n/num 8797879802")
    else:
        await q.answer("❌ Join both channels first", show_alert=True)

# ───────── COMMANDS ─────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)

    if not await is_joined(update.effective_user.id, context):
        await update.message.reply_text(
            "🚫 Join both channels to use this bot",
            reply_markup=join_keyboard()
        )
        return

    await update.message.reply_text("👋 Welcome!\nUse:\n/num 8797879802")

async def num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage:\n/num 8797879802")
        return

    if not await is_joined(update.effective_user.id, context):
        await update.message.reply_text(
            "🚫 Join both channels",
            reply_markup=join_keyboard()
        )
        return

    for mobile in context.args:
        await lookup(update, context, mobile)

async def lookup(update, context, mobile):
    inc_lookup()

    if not mobile.isdigit():
        await update.message.reply_text(f"❌ Invalid number: {mobile}")
        return

    try:
        r = requests.get(
            f"{BASE_URL}?key={API_KEY}&num={mobile}",
            timeout=20
        ).json()
    except:
        await update.message.reply_text("⚠️ API error")
        return

    if not r.get("success"):
        await update.message.reply_text("❌ No data found")
        return

    results = r.get("result", [])
    lines = [f"📱 Number: {mobile}", "-" * 40]

    for i, x in enumerate(results, 1):
        lines += [
            f"\n📌 Record {i}",
            f"Name: {x.get('name','N/A')}",
            f"Father: {x.get('father_name','N/A')}",
            f"Alt: {x.get('alt_mobile','N/A')}",
            f"Circle: {x.get('circle','N/A')}",
            f"Email: {x.get('email','N/A')}",
            f"Address: {x.get('address','N/A')}",
        ]

    fname = f"lookup_{mobile}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(fname, "rb") as f:
        msg = await update.message.reply_document(f)

    await asyncio.sleep(60)

    try:
        await msg.delete()
        os.remove(fname)
    except:
        pass

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mem = psutil.virtual_memory()
    await update.message.reply_text(
        f"🏓 Pong\n"
        f"⏱ Uptime: {uptime()}\n"
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

# ───────── TELEGRAM APP ─────────

application = ApplicationBuilder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("num", num))
application.add_handler(CommandHandler("ping", ping))
application.add_handler(CommandHandler("stats", stats))
application.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))

# ───────── FLASK WEBHOOK ─────────

flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def home():
    return "Bot running", 200

@flask_app.route(f"/{WEBHOOK_PATH}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "OK", 200

@flask_app.before_first_request
def set_webhook():
    application.bot.set_webhook(f"{APP_URL}/{WEBHOOK_PATH}")
    print("✅ Webhook set")

# ───────── RUN ─────────

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
