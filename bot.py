import asyncio
import secrets
import logging
import os
from database import connect, initialize, PostgresConnection
from datetime import datetime, timezone
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

AGENCY_NAME = "Emmanuel Digitals & CO"
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
ADMIN_USER_IDS = {int(value.strip()) for value in os.environ.get("ADMIN_USER_IDS", "").split(",") if value.strip()}
if ADMIN_CHAT_ID > 0:
    ADMIN_USER_IDS.add(ADMIN_CHAT_ID)

PORTFOLIO_URL = os.environ.get("PORTFOLIO_URL", "https://t.me/Emmanuel_DigitalsCO")
CONTACT_URL = os.environ.get("CONTACT_URL", "https://t.me/EmmanuelDigitals_CO")
DB_PATH = os.environ.get("DB_PATH", "leads.db")

ABOUT_TEXT = (
    "Emmanuel Digitals & CO is a digital growth and automation agency helping global brands "
    "scale through social media marketing, paid advertising, custom bots, workflow automation, "
    "and crypto/forex marketing."
)

SERVICES_TEXT = (
    "<b>Our Services</b>\n\n"
    "• <b>Social Media Marketing</b> — content strategy, audience growth and community management.\n"
    "• <b>Paid Advertising & Telegram Ads</b> — Telegram, Meta, Google and TikTok campaigns.\n"
    "• <b>Automation & Custom Bots</b> — Telegram bots, lead capture and business workflows.\n"
    "• <b>Crypto & Forex Marketing</b> — growth solutions for trading, crypto and fintech brands."
)

STATUS_LABELS = {
    "new": "🆕 New",
    "contacted": "📞 Contacted",
    "progress": "🔄 In Progress",
    "closed": "✅ Closed",
}


def db_connection():
    conn = connect(DB_PATH)
    try:
        initialize(conn)
    except Exception:
        conn.close()
        raise
    return conn



def create_lead(user) -> int:
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    conn = db_connection()
    cur = conn.execute(
        "INSERT INTO leads (user_id, name, username, created_at) VALUES (?, ?, ?, ?) RETURNING id",
        (user.id, user.full_name, user.username or "", created_at),
    )
    lead_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return int(lead_id)


def set_status(lead_id: int, status: str) -> None:
    conn = db_connection()
    conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
    conn.commit()
    conn.close()


def get_lead(lead_id: int):
    conn = db_connection()
    row = conn.execute(
        "SELECT id, user_id, name, username, created_at, status FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()
    conn.close()
    return row


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("About Agency", callback_data="about")],
        [InlineKeyboardButton("Our Services", callback_data="services")],
        [InlineKeyboardButton("Portfolio", url=PORTFOLIO_URL)],
        [InlineKeyboardButton("Send a Request", callback_data="request")],
    ])


def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back to Home", callback_data="home")]])


def lead_admin_keyboard(lead_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Reply to Client", callback_data=f"reply:{user_id}")],
        [
            InlineKeyboardButton("Contacted", callback_data=f"status:{lead_id}:contacted"),
            InlineKeyboardButton("In Progress", callback_data=f"status:{lead_id}:progress"),
        ],
        [InlineKeyboardButton("Close Lead", callback_data=f"status:{lead_id}:closed")],
    ])


def is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id in ADMIN_USER_IDS)



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type == "private":
        save_user(update.effective_user)
    context.user_data.clear()
    await update.effective_message.reply_text(
        f"<b>{AGENCY_NAME}</b>\n\n"
        "Digital growth, marketing and automation for ambitious brands.\n\n"
        "Explore our services, view our portfolio, or send your project or issue directly to our team.",
        parse_mode=ParseMode.HTML,
        reply_markup=home_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        f"<b>{AGENCY_NAME}</b>\n\nUse /start to return home.\nUse Send a Request to contact our team directly.",
        parse_mode=ParseMode.HTML,
        reply_markup=home_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.effective_message.reply_text(
        "Request cancelled.", reply_markup=home_keyboard()
    )


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if update.effective_chat.type == "private":
        save_user(update.effective_user)
    if await admin_callback(update, context):
        return
    await query.answer()
    data = query.data or ""

    if data == "home":
        context.user_data.clear()
        await query.edit_message_text(
            f"<b>{AGENCY_NAME}</b>\n\n"
            "Digital growth, marketing and automation for ambitious brands.\n\n"
            "Explore our services, view our portfolio, or send your project or issue directly to our team.",
            parse_mode=ParseMode.HTML,
            reply_markup=home_keyboard(),
        )
        return

    if data == "about":
        await query.edit_message_text(
            f"<b>About {AGENCY_NAME}</b>\n\n{ABOUT_TEXT}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard(),
        )
        return

    if data == "services":
        await query.edit_message_text(
            SERVICES_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard(),
        )
        return

    if data == "request":
        context.user_data.clear()
        context.user_data["awaiting_request"] = True
        await query.edit_message_text(
            "<b>Send a Request</b>\n\n"
            "Tell us about your issue, project, goal, or the service you need. "
            "Send your message here and it will be forwarded directly to our team.\n\n"
            "You can send text, a photo, document, or other supported Telegram message.\n\n"
            "Use /cancel to cancel.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard(),
        )
        return

    if data.startswith("reply:"):
        if not is_admin(update):
            await query.answer("Admin access only.", show_alert=True)
            return
        target_user_id = int(data.split(":", 1)[1])
        context.user_data["reply_to_user"] = target_user_id
        await query.message.reply_text(
            f"<b>Reply mode enabled</b>\n\nSend your message now. It will be delivered to Telegram user <code>{target_user_id}</code>.\n\nUse /cancel to exit.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("status:"):
        if not is_admin(update):
            await query.answer("Admin access only.", show_alert=True)
            return
        _, lead_id_text, status = data.split(":", 2)
        lead_id = int(lead_id_text)
        lead = get_lead(lead_id)
        if not lead:
            await query.answer("Lead not found.", show_alert=True)
            return
        set_status(lead_id, status)
        await query.edit_message_reply_markup(
            reply_markup=lead_admin_keyboard(lead_id, lead[1])
        )
        await query.answer(f"Lead #{lead_id}: {STATUS_LABELS[status]}")


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_admin(update) or "reply_to_user" not in context.user_data:
        return False

    target_user_id = context.user_data["reply_to_user"]
    try:
        await update.effective_message.copy(chat_id=target_user_id)
        await update.effective_message.reply_text("Reply delivered to the client.")
    except Exception:
        logging.exception("Failed to deliver admin reply")
        await update.effective_message.reply_text(
            "I couldn't deliver that reply. The client may have blocked the bot."
        )
    finally:
        context.user_data.pop("reply_to_user", None)
    return True


async def receive_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type == "private":
        save_user(update.effective_user)
    if await admin_message(update, context):
        return
    if await handle_admin_reply(update, context):
        return

    if not context.user_data.get("awaiting_request"):
        return

    if not ADMIN_CHAT_ID:
        logging.error("ADMIN_CHAT_ID is not configured")
        await update.effective_message.reply_text(
            "Requests are temporarily unavailable. Please try again later."
        )
        return

    user = update.effective_user
    message = update.effective_message
    lead_id = create_lead(user)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    username = f"@{user.username}" if user.username else "Not set"
    name = escape(user.full_name)

    header = (
        f"<b>NEW CLIENT REQUEST · #{lead_id}</b>\n\n"
        f"Client: {name}\n"
        f"Username: {escape(username)}\n"
        f"Telegram ID: <code>{user.id}</code>\n"
        f"Received: {timestamp}\n"
        f"Status: {STATUS_LABELS['new']}\n\n"
        "<b>REQUEST</b>"
    )

    sent = await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=header,
        parse_mode=ParseMode.HTML,
        reply_markup=lead_admin_keyboard(lead_id, user.id),
    )
    await message.copy(chat_id=ADMIN_CHAT_ID, reply_to_message_id=sent.message_id)

    context.user_data.clear()
    await message.reply_text(
        f"<b>Request received</b>\n\n"
        f"Thank you for contacting <b>{AGENCY_NAME}</b>. Your request has been sent directly to our team. "
        "We'll review it and get back to you.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_home_keyboard(),
    )


async def leads_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return

    conn = db_connection()
    rows = conn.execute(
        "SELECT id, name, username, status, created_at FROM leads ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()

    if not rows:
        await update.effective_message.reply_text("No leads yet.")
        return

    lines = ["<b>Recent Leads</b>", ""]
    for lead_id, name, username, status, created_at in rows:
        handle = f"@{username}" if username else "no username"
        lines.append(
            f"#{lead_id} · {escape(name)} · {escape(handle)} · {STATUS_LABELS.get(status, status)} · {created_at}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Unhandled bot error", exc_info=context.error)


def save_user(user):
    if not user or user.is_bot:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = db_connection()
    conn.execute("""INSERT INTO users(user_id,name,username,first_seen,last_seen)
        VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
        name=excluded.name, username=excluded.username, last_seen=excluded.last_seen, blocked=0""",
        (user.id, user.full_name, user.username or "", now, now))
    conn.commit()
    conn.close()


def recipients():
    conn = db_connection()
    rows = conn.execute("SELECT user_id FROM users WHERE subscribed=1 AND blocked=0 ORDER BY user_id").fetchall()
    conn.close()
    return [row[0] for row in rows if row[0] not in ADMIN_USER_IDS]


def user_exists(user_id):
    conn = db_connection()
    row = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row)


def update_user_flag(user_id, *, subscribed=None, blocked=None):
    conn = db_connection()
    if subscribed is not None:
        conn.execute("UPDATE users SET subscribed=? WHERE user_id=?", (int(subscribed), user_id))
    if blocked is not None:
        conn.execute("UPDATE users SET blocked=? WHERE user_id=?", (int(blocked), user_id))
    conn.commit()
    conn.close()


async def stop_messages(update, context):
    if update.effective_chat.type != "private":
        return
    save_user(update.effective_user)
    update_user_flag(update.effective_user.id, subscribed=False)
    await update.effective_message.reply_text("Agency broadcasts stopped. Use /subscribe to receive them again.")


async def subscribe_messages(update, context):
    if update.effective_chat.type != "private":
        return
    save_user(update.effective_user)
    update_user_flag(update.effective_user.id, subscribed=True)
    await update.effective_message.reply_text("Agency broadcasts enabled. Use /stop to unsubscribe.")


async def admin_panel(update, context):
    if not is_admin(update):
        return
    context.user_data.clear()
    conn = db_connection()
    total, subscribed, blocked = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(subscribed),0), COALESCE(SUM(blocked),0) FROM users"
    ).fetchone()
    conn.close()
    await update.effective_message.reply_text(
        f"Admin panel\nSaved users: {total}\nSubscribed: {subscribed}\nBlocked/unreachable: {blocked}\nBroadcast recipients: {len(recipients())}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Broadcast to users", callback_data="admin:broadcast")],
            [InlineKeyboardButton("Message one user", callback_data="admin:direct")],
            [InlineKeyboardButton("Recent users", callback_data="admin:users")],
        ]),
    )


async def admin_callback(update, context):
    query = update.callback_query
    data = query.data or ""
    if not data.startswith("admin:"):
        return False
    if not is_admin(update):
        await query.answer("Admin access only.", show_alert=True)
        return True
    await query.answer()
    action = data.split(":", 1)[1]
    if action == "users":
        conn = db_connection()
        rows = conn.execute("SELECT user_id,name,username FROM users ORDER BY last_seen DESC LIMIT 20").fetchall()
        conn.close()
        text = "Recent users\n" + "\n".join(f"{uid} | {name[:60]} | @{username}" for uid, name, username in rows)
        await query.message.reply_text(text if rows else "No saved users yet.")
    elif action in {"broadcast", "direct"}:
        context.user_data.clear()
        context.user_data["admin_mode"] = "content" if action == "broadcast" else "target"
        context.user_data["admin_target"] = "all" if action == "broadcast" else None
        await query.message.reply_text(
            "Send the text, photo, video or document to broadcast. A preview and confirmation follow. /cancel to exit."
            if action == "broadcast" else "Send the saved user's numeric Telegram ID. /cancel to exit."
        )
    elif action.startswith("send:"):
        if action.split(":", 1)[1] != context.user_data.get("draft_token"):
            await query.message.reply_text("This confirmation has expired. Use the newest preview.")
            return True
        draft = context.user_data.pop("admin_draft", None)
        if not draft:
            await query.message.reply_text("This draft has expired or was already sent. Open /admin again.")
            return True
        if context.application.bot_data.get("sending"):
            context.user_data["admin_draft"] = draft
            await query.message.reply_text("A delivery is already running. Try again after it finishes.")
            return True
        context.application.bot_data["sending"] = True
        context.user_data.pop("admin_mode", None)
        context.application.create_task(deliver_messages(context, draft, query.message.chat_id))
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Delivery started. You will receive a delivery report.")
    elif action == "cancel":
        context.user_data.clear()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Draft cancelled.")
    return True


async def admin_message(update, context):
    if not is_admin(update):
        return False
    mode = context.user_data.get("admin_mode")
    if mode == "target":
        try:
            target = int(update.effective_message.text or "")
        except ValueError:
            target = 0
        if not user_exists(target):
            await update.effective_message.reply_text("Enter a numeric ID from the saved users list.")
            return True
        context.user_data["admin_target"] = target
        context.user_data["admin_mode"] = "content"
        await update.effective_message.reply_text("Send your custom message or media. A preview and confirmation follow.")
        return True
    if mode == "content":
        message = update.effective_message
        try:
            await message.copy(chat_id=message.chat_id)
        except TelegramError:
            await message.reply_text("This message cannot be copied. Send text, a photo, video or document instead.")
            return True
        target = context.user_data["admin_target"]
        context.user_data["draft_token"] = secrets.token_hex(8)
        context.user_data["admin_draft"] = {"chat_id": message.chat_id, "message_id": message.message_id, "target": target}
        context.user_data["admin_mode"] = "confirm"
        audience = f"{len(recipients())} subscribed users" if target == "all" else f"user {target}"
        await message.reply_text(f"Preview above. Send to {audience}?",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Send", callback_data=f"admin:send:{context.user_data['draft_token']}"),
                InlineKeyboardButton("Cancel", callback_data="admin:cancel"),
            ]]))
        return True
    if mode == "confirm":
        await update.effective_message.reply_text("Use Send or Cancel on the draft, or /cancel.")
        return True
    return False


async def deliver_messages(context, draft, report_chat_id):
    sent = failed = skipped = 0
    try:
        targets = recipients() if draft["target"] == "all" else [draft["target"]]
        for uid in targets:
            if draft["target"] == "all" and uid not in recipients():
                skipped += 1
                continue
            for attempt in range(3):
                try:
                    await context.bot.copy_message(chat_id=uid, from_chat_id=draft["chat_id"], message_id=draft["message_id"])
                    sent += 1
                    break
                except RetryAfter as exc:
                    if attempt == 2:
                        failed += 1
                        break
                    delay = exc.retry_after
                    await asyncio.sleep((delay.total_seconds() if hasattr(delay, "total_seconds") else float(delay)) + 1)
                except Forbidden:
                    update_user_flag(uid, blocked=True)
                    failed += 1
                    break
                except TelegramError:
                    logging.exception("Message delivery failed for user %s", uid)
                    failed += 1
                    break
            await asyncio.sleep(0.05)
        await context.bot.send_message(chat_id=report_chat_id, text=f"Delivery finished. Sent: {sent}; failed: {failed}; skipped: {skipped}.")
    finally:
        context.application.bot_data["sending"] = False


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # HTTP request URLs include the Telegram bot token. Do not log them.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    db_connection().close()

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("stop", stop_messages))
    application.add_handler(CommandHandler("subscribe", subscribe_messages))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("leads", leads_command))
    application.add_handler(CallbackQueryHandler(callbacks))
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, receive_request)
    )
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

