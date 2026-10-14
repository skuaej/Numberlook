import os
import threading
import asyncio
from datetime import datetime, timedelta

import requests
import psutil
from pymongo import MongoClient
from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# ───────── CONFIG ─────────

BOT_TOKEN = "8955302399:AAG-sGnndn9ry7NggOemqdgt8YOOUxAiP7U"
MONGO_URI = "mongodb+srv://usaomega1_db_user:Masdt2qYlJfXs20N@cluster0.zpedlcp.mongodb.net/?appName=Cluster0"
OWNER_ID = 6804892450

BASE_URL = "https://number-look-production.up.railway.app/FetchData"

FORCE_CHAT_IDS = [-1004351097681, -1003732085864]
JOIN_LINKS = [
    "https://t.me/+dOIP895nySo3NmZl",
    "https://t.me/+qwSbF4jNEMIwZDE1"
]

BOT_START = datetime.now()
COOLDOWN_SECONDS = 60

# ───────── DATABASE ─────────

mongo = MongoClient(MONGO_URI)
db = mongo["eyelookup_bot"]
users_col = db["users"]
stats_col = db["stats"]
cooldown_col = db["cooldown"]

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

def is_on_cooldown(user_id: int) -> tuple[bool, int]:
    doc = cooldown_col.find_one({"user_id": user_id})
    if not doc:
        return False, 0

    last_time = doc.get("last_search")
    if not last_time:
        return False, 0

    elapsed = (datetime.now() - last_time).total_seconds()
    remaining = COOLDOWN_SECONDS - elapsed

    if remaining > 0:
        return True, int(remaining)
    return False, 0

def set_cooldown(user_id: int):
    cooldown_col.update_one(
        {"user_id": user_id},
        {"$set": {"last_search": datetime.now()}},
        upsert=True
    )

# ───────── FORCE JOIN ─────────

async def is_joined(user_id, context):
    for chat_id in FORCE_CHAT_IDS:
        try:
            m = await context.bot.get_chat_member(chat_id, user_id)
            if m.status in ("left", "kicked"):
                return False
        except Exception as e:
            print(f"⚠️ Membership check failed for chat {chat_id}: {e}")
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

    user_id = update.effective_user.id

    if not await is_joined(user_id, context):
        await update.message.reply_text(
            "🚫 Join both channels",
            reply_markup=join_keyboard()
        )
        return

    # Cooldown check
    on_cd, remaining = is_on_cooldown(user_id)
    if on_cd:
        await update.message.reply_text(
            f"⏳ You are on cooldown!\nPlease wait **{remaining} seconds** before next search.",
            parse_mode="Markdown"
        )
        return

    for mobile in context.args:
        await lookup(update, context, mobile)

async def lookup(update, context, mobile):
    user_id = update.effective_user.id
    inc_lookup()

    if not mobile.isdigit():
        await update.message.reply_text(f"❌ Invalid number: {mobile}")
        return

    progress_msg = await update.message.reply_text(
        f"🔎 Searching database for `{mobile}`...",
        parse_mode="Markdown"
    )

    try:
        response = requests.get(
            BASE_URL,
            params={"Number": mobile},
            timeout=30
        )
        print("Status:", response.status_code)
        print("Response Text:", response.text[:700])
        r = response.json()
    except Exception as e:
        print(f"❌ API Error: {e}")
        await progress_msg.edit_text("⚠️ API error occurred.")
        return

    # ───────── Parser ─────────
    results = []
    developer = None

    if isinstance(r, list):
        results = r
    elif isinstance(r, dict):
        developer = r.get("Developer") or r.get("developer")

        data = r.get("Data") or r.get("data")
        if isinstance(data, dict):
            main = data.get("Main_Records") or data.get("main_records") or []
            alt  = data.get("Alt_Records")  or data.get("alt_records")  or []
            results = main + alt
        elif isinstance(data, list):
            results = data

        if not results:
            for key in ["result", "data", "records", "details", "Main_Records", "main_records"]:
                if key in r and isinstance(r[key], list):
                    results = r[key]
                    break

        if not results:
            if any(k in r for k in ('name', 'fname', 'father_name', 'circle', 'address', 'email', 'mobile', 'Number', 'id')):
                results = [r]
            else:
                for v in r.values():
                    if isinstance(v, list) and v:
                        results = v
                        break

    if not results:
        await progress_msg.edit_text("❌ No data found.")
        return

    # Set cooldown only after successful result
    set_cooldown(user_id)

    lines = [f"📱 Number: {mobile}", "-" * 40]

    for i, x in enumerate(results, 1):
        lines += [
            f"\n📌 Record {i}",
            f"Name: {x.get('name') or 'N/A'}",
            f"Father: {x.get('fname') or x.get('father_name') or 'N/A'}",
            f"Alt: {x.get('alt') or x.get('alt_mobile') or 'N/A'}",
            f"Circle: {x.get('circle') or 'N/A'}",
            f"Email: {x.get('email') or 'N/A'}",
            f"ID: {x.get('id') or 'N/A'}",
            f"Address: {x.get('address') or 'N/A'}",
        ]

    if developer:
        lines += [
            "",
            "-" * 40,
            f"Developer: {developer}"
        ]

    fname = f"lookup_{mobile}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    await progress_msg.delete()

    # Send result file
    with open(fname, "rb") as f:
        doc_msg = await update.message.reply_document(f)

    # Send short text
    text_msg = await update.message.reply_text("✅ Result ready")

    # Delete both after 1 minute
    await asyncio.sleep(60)

    try:
        await doc_msg.delete()
        await text_msg.delete()
        os.remove(fname)
    except Exception:
        pass

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mem = psutil.virtual_memory()
    await update.message.reply_text(
        f"🏓 Pong\n"
        f"⏱ Uptime: {uptime()}\n"
        f"💾 RAM: {mem.percent}%"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    users = users_col.count_documents({})
    s = stats_col.find_one({"date": today}) or {"lookups": 0}

    await update.message.reply_text(
        f"📊 Stats\n"
        f"👥 Users: {users}\n"
        f"🔍 Lookups Today: {s['lookups']}"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return

    message_to_broadcast = update.message.reply_to_message
    if not message_to_broadcast and not context.args:
        await update.message.reply_text("❌ Reply to a message or provide text: /bc <text>")
        return

    text = " ".join(context.args) if context.args else None
    all_users = users_col.find({})
    success, failed = 0, 0

    status_msg = await update.message.reply_text("📢 Broadcasting message...")

    for user in all_users:
        user_id = user.get("user_id")
        try:
            if message_to_broadcast:
                await message_to_broadcast.copy(chat_id=user_id)
            else:
                await context.bot.send_message(chat_id=user_id, text=text)
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(f"✅ Broadcast Complete!\nSuccessful: {success}\nFailed: {failed}")

# ───────── KEEP-ALIVE SERVER ─────────

flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def home():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# ───────── MAIN APP ─────────

def main():
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("num", num))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("bc", broadcast))
    application.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))

    print("🤖 Bot is starting via polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
