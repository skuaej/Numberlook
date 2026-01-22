import requests
import os
import asyncio
from datetime import datetime
from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

# ---------------- CONFIG ----------------

API_KEY = "jakiez"
BASE_URL = "https://giga-seven.vercel.app/api"

BOT_TOKEN = os.getenv("BOT_TOKEN")  # set in Koyeb env
PORT = int(os.getenv("PORT", 8000))

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # set in Koyeb env

# ---- Forced join chats ----
FORCE_CHAT_IDS = [
    -1003559174618,   # Eye look discussion
    -1003317410802    # Eye look
]

JOIN_LINKS = [
    "https://t.me/+BkMdZGT0ryBkMThl",
    "https://t.me/+HidgJvH0BktiZmI9"
]

# ---------------- APP INIT ----------------

flask_app = Flask(__name__)
tg_app = ApplicationBuilder().token(BOT_TOKEN).build()


# ---------------- Forced Join Logic ----------------

async def is_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    for chat_id in FORCE_CHAT_IDS:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception:
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
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=join_keyboard()
        )
    else:
        await update.callback_query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=join_keyboard()
        )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if await is_user_joined(user_id, context):
        await query.message.edit_text(
            "✅ Verified!\n\n"
            "Now use:\n"
            "/getnumber 8797879802\n"
            "@eyelookup 8797879802"
        )
    else:
        await query.answer(
            "❌ Still not verified.\n\n"
            "Make sure:\n"
            "• You joined BOTH channels\n"
            "• Bot is admin there\n"
            "• Try again after 10 seconds",
            show_alert=True
        )


# ---------------- Bot Commands ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_user_joined(user_id, context):
        await force_join_message(update, context)
        return

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Lookup commands:\n"
        "/getnumber 8797879802\n"
        "@eyelookup 8797879802"
    )


async def lookup_one(update: Update, context: ContextTypes.DEFAULT_TYPE, mobile: str):
    if not mobile.isdigit():
        await update.message.reply_text(f"❌ Invalid number: {mobile}")
        return

    if not (8 <= len(mobile) <= 13):
        await update.message.reply_text(f"❌ Invalid length: {mobile}")
        return

    url = f"{BASE_URL}?key={API_KEY}&num={mobile}"

    r = requests.get(url, timeout=20)
    data = r.json()

    if not data.get("success"):
        await update.message.reply_text(
            f"⚠️ API Error for {mobile}:\n{data.get('message', 'Unknown error')}"
        )
        return

    results = data.get("result")
    if not results or not isinstance(results, list):
        await update.message.reply_text(f"❌ No data found for {mobile}.")
        return

    # ---- build text ----
    lines = []
    lines.append("📱 Mobile Lookup Result")
    lines.append(f"🔍 Searched Number: {mobile}")
    lines.append(f"🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 50)

    for idx, info in enumerate(results, start=1):
        name = info.get("name", "").strip() or "N/A"
        father = info.get("father_name", "").strip() or "N/A"
        mobile_no = info.get("mobile", "").strip() or "N/A"
        alt = info.get("alt_mobile", "").strip() or "N/A"
        circle = info.get("circle", "").strip() or "N/A"
        email = info.get("email", "").strip() or "N/A"
        address = info.get("address", "").strip() or "N/A"

        lines.append(f"\n📌 Record {idx}")
        lines.append(f"Name        : {name}")
        lines.append(f"Father Name: {father}")
        lines.append(f"Mobile      : {mobile_no}")
        lines.append(f"Alt Mobile  : {alt}")
        lines.append(f"Circle      : {circle}")
        lines.append(f"Email       : {email}")
        lines.append(f"Address     : {address}")
        lines.append("-" * 50)

    # ---- footer ----
    lines.append("")
    lines.append("Join us @eyelookup_bot")
    lines.append("Join our channels:")
    lines.append(JOIN_LINKS[0])
    lines.append(JOIN_LINKS[1])

    text_content = "\n".join(lines)

    filename = f"lookup_{mobile}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(text_content)

    with open(filename, "rb") as f:
        file_msg = await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"📄 Mobile lookup result for {mobile}"
        )

    warn_msg = await update.message.reply_text(
        "⚠️ Save this details.\n"
        "This file will be deleted in 30 seconds."
    )

    await asyncio.sleep(30)

    try:
        await context.bot.delete_message(update.effective_chat.id, file_msg.message_id)
    except:
        pass

    try:
        await context.bot.delete_message(update.effective_chat.id, warn_msg.message_id)
    except:
        pass

    try:
        os.remove(filename)
    except:
        pass


async def do_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE, mobiles: list):
    user_id = update.effective_user.id

    if not await is_user_joined(user_id, context):
        await force_join_message(update, context)
        return

    for mobile in mobiles:
        await lookup_one(update, context, mobile)


async def getnumber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Usage:\n/getnumber 8797879802\nor\n@eyelookup 8797879802"
        )
        return

    await do_lookup(update, context, context.args)


async def mention_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    nums = text.replace("@eyelookup", "").strip().split()

    if not nums:
        await update.message.reply_text("❌ Usage:\n@eyelookup 8797879802")
        return

    await do_lookup(update, context, nums)


# ---------------- Register Handlers ----------------

tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("getnumber", getnumber))
tg_app.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))
tg_app.add_handler(
    MessageHandler(filters.TEXT & filters.Regex(r"@eyelookup"), mention_lookup)
)


# ---------------- Webhook Route ----------------

@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), tg_app.bot)
    tg_app.update_queue.put_nowait(update)
    return "ok"


# ---------------- Startup ----------------

if __name__ == "__main__":
    async def main():
        await tg_app.initialize()
        await tg_app.bot.set_webhook(WEBHOOK_URL)
        print("✅ Webhook set:", WEBHOOK_URL)

    asyncio.run(main())

    flask_app.run(host="0.0.0.0", port=PORT)
