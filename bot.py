import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from config import BOT_TOKEN, ADMIN_IDS
from database import Database

# הגדרת לוגים
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# שלבי שיחה
BROADCAST_MESSAGE, BROADCAST_CONFIRM = range(2)
ADD_CHANNEL, REMOVE_CHANNEL = range(2, 4)
BAN_USER, UNBAN_USER = range(4, 6)

db = Database()

# ===================== פונקציות עזר =====================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("⛔ אין לך הרשאה לפקודה זו.")
            return
        return await func(update, context)
    return wrapper

# ===================== תפריט ראשי =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username or "", user.first_name or "")

    if is_admin(user.id):
        await show_admin_panel(update, context)
    else:
        keyboard = [[InlineKeyboardButton("📢 ערוצים וקבוצות", callback_data="show_channels")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👋 שלום {user.first_name}!\nברוך הבא לבוט שלנו.",
            reply_markup=reply_markup
        )

# ===================== פאנל אדמין =====================

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📢 פרסום להכל", callback_data="broadcast"),
         InlineKeyboardButton("📋 ניהול ערוצים", callback_data="manage_channels")],
        [InlineKeyboardButton("👥 ניהול משתמשים", callback_data="manage_users"),
         InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")],
        [InlineKeyboardButton("🔔 הודעה לאדמין", callback_data="admin_msg")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "🛠 *פאנל ניהול אדמין*\n\nבחר פעולה:"

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# ===================== פרסום =====================

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="admin_panel")]]
    await query.edit_message_text(
        "📢 *שלח את ההודעה לפרסום:*\n\n"
        "תוכל לשלוח:\n"
        "• טקסט\n• תמונה עם כיתוב\n• וידאו עם כיתוב\n\n"
        "_הפרסום יישלח לכל הערוצים והמשתמשים הרשומים_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return BROADCAST_MESSAGE

async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    context.user_data['broadcast_msg'] = update.message

    channels = db.get_channels()
    users_count = db.get_users_count()
    channels_text = "\n".join([f"• {ch['name']}" for ch in channels]) if channels else "• אין ערוצים רשומים"

    keyboard = [
        [InlineKeyboardButton("✅ אשר פרסום", callback_data="confirm_broadcast"),
         InlineKeyboardButton("❌ ביטול", callback_data="admin_panel")]
    ]
    await update.message.reply_text(
        f"📋 *אישור פרסום:*\n\n"
        f"👥 משתמשים: {users_count}\n"
        f"📢 ערוצים:\n{channels_text}\n\n"
        f"האם לשלוח?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    msg = context.user_data.get('broadcast_msg')
    if not msg:
        await query.edit_message_text("❌ שגיאה: לא נמצאה הודעה לפרסום.")
        return ConversationHandler.END

    channels = db.get_channels()
    users = db.get_all_users()

    success = 0
    failed = 0

    # שליחה לערוצים
    for channel in channels:
        try:
            if msg.photo:
                await context.bot.send_photo(channel['chat_id'], msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await context.bot.send_video(channel['chat_id'], msg.video.file_id, caption=msg.caption)
            else:
                await context.bot.send_message(channel['chat_id'], msg.text)
            success += 1
        except Exception as e:
            logger.error(f"Failed to send to channel {channel['chat_id']}: {e}")
            failed += 1

    # שליחה למשתמשים
    for user in users:
        try:
            if msg.photo:
                await context.bot.send_photo(user['user_id'], msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await context.bot.send_video(user['user_id'], msg.video.file_id, caption=msg.caption)
            else:
                await context.bot.send_message(user['user_id'], msg.text)
            success += 1
            await asyncio.sleep(0.05)  # מניעת חסימה
        except Exception as e:
            failed += 1

    await query.edit_message_text(
        f"✅ *פרסום הושלם!*\n\n"
        f"✔️ נשלח בהצלחה: {success}\n"
        f"❌ נכשל: {failed}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ===================== ניהול ערוצים =====================

async def manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    channels = db.get_channels()
    channels_text = "\n".join([f"• {ch['name']} (`{ch['chat_id']}`)" for ch in channels]) if channels else "אין ערוצים רשומים"

    keyboard = [
        [InlineKeyboardButton("➕ הוסף ערוץ/קבוצה", callback_data="add_channel")],
        [InlineKeyboardButton("➖ הסר ערוץ/קבוצה", callback_data="remove_channel")],
        [InlineKeyboardButton("🔙 חזור", callback_data="admin_panel")]
    ]
    await query.edit_message_text(
        f"📋 *ניהול ערוצים וקבוצות*\n\n{channels_text}\n\n"
        f"_להוסיף ערוץ: הוסף את הבוט כאדמין בערוץ/קבוצה ואז לחץ הוסף_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="manage_channels")]]
    await query.edit_message_text(
        "➕ *הוספת ערוץ/קבוצה*\n\n"
        "שלח את ה-Chat ID של הערוץ/קבוצה.\n\n"
        "📌 *איך מוצאים את ה-ID?*\n"
        "1. הוסף את הבוט `@userinfobot` לערוץ/קבוצה\n"
        "2. הוא ישלח את ה-ID\n"
        "3. העתק ושלח כאן (לדוגמה: `-1001234567890`)",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ADD_CHANNEL

async def add_channel_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_text = update.message.text.strip()
    try:
        chat_id = int(chat_id_text)
        chat = await context.bot.get_chat(chat_id)
        db.add_channel(chat_id, chat.title or str(chat_id))
        await update.message.reply_text(f"✅ הערוץ/קבוצה *{chat.title}* נוסף בהצלחה!", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ ID לא תקין. שלח מספר בלבד.")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {str(e)}\n\nוודא שהבוט הוסף כאדמין.")
    return ConversationHandler.END

async def remove_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    channels = db.get_channels()
    if not channels:
        await query.edit_message_text("❌ אין ערוצים להסרה.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_channels")]]))
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"🗑 {ch['name']}", callback_data=f"del_channel_{ch['chat_id']}")] for ch in channels]
    keyboard.append([InlineKeyboardButton("❌ ביטול", callback_data="manage_channels")])
    await query.edit_message_text("בחר ערוץ להסרה:", reply_markup=InlineKeyboardMarkup(keyboard))
    return REMOVE_CHANNEL

async def remove_channel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.replace("del_channel_", ""))
    db.remove_channel(chat_id)
    await query.edit_message_text("✅ הערוץ הוסר בהצלחה!")
    return ConversationHandler.END

# ===================== ניהול משתמשים =====================

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    users_count = db.get_users_count()
    banned_count = db.get_banned_count()

    keyboard = [
        [InlineKeyboardButton("🚫 חסום משתמש", callback_data="ban_user"),
         InlineKeyboardButton("✅ שחרר חסום", callback_data="unban_user")],
        [InlineKeyboardButton("📋 רשימת חסומים", callback_data="list_banned")],
        [InlineKeyboardButton("🔙 חזור", callback_data="admin_panel")]
    ]
    await query.edit_message_text(
        f"👥 *ניהול משתמשים*\n\n"
        f"👤 סה\"כ משתמשים: {users_count}\n"
        f"🚫 חסומים: {banned_count}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def ban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="manage_users")]]
    await query.edit_message_text(
        "🚫 *חסימת משתמש*\n\nשלח את ה-User ID לחסימה:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return BAN_USER

async def ban_user_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text.strip())
        db.ban_user(user_id)
        await update.message.reply_text(f"✅ המשתמש `{user_id}` נחסם.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ ID לא תקין.")
    return ConversationHandler.END

async def unban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="manage_users")]]
    await query.edit_message_text(
        "✅ *שחרור חסום*\n\nשלח את ה-User ID לשחרור:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return UNBAN_USER

async def unban_user_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text.strip())
        db.unban_user(user_id)
        await update.message.reply_text(f"✅ המשתמש `{user_id}` שוחרר.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ ID לא תקין.")
    return ConversationHandler.END

async def list_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    banned = db.get_banned_users()
    if not banned:
        text = "✅ אין משתמשים חסומים."
    else:
        text = "🚫 *משתמשים חסומים:*\n\n" + "\n".join([f"• `{u['user_id']}`" for u in banned])
    keyboard = [[InlineKeyboardButton("🔙 חזור", callback_data="manage_users")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ===================== סטטיסטיקות =====================

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    users_count = db.get_users_count()
    channels_count = len(db.get_channels())
    banned_count = db.get_banned_count()

    keyboard = [[InlineKeyboardButton("🔙 חזור", callback_data="admin_panel")]]
    await query.edit_message_text(
        f"📊 *סטטיסטיקות הבוט*\n\n"
        f"👤 משתמשים רשומים: {users_count}\n"
        f"📢 ערוצים/קבוצות: {channels_count}\n"
        f"🚫 משתמשים חסומים: {banned_count}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ===================== הצגת ערוצים למשתמש =====================

async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get_channels()
    if not channels:
        await query.edit_message_text("אין ערוצים/קבוצות עדיין.")
        return
    keyboard = [[InlineKeyboardButton(f"📢 {ch['name']}", url=f"https://t.me/{ch['username']}")] for ch in channels if ch.get('username')]
    keyboard.append([InlineKeyboardButton("🔙 חזור", callback_data="back_start")])
    await query.edit_message_text("📢 *הערוצים והקבוצות שלנו:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ===================== callback handler =====================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "admin_panel":
        await show_admin_panel(update, context)
    elif data == "manage_channels":
        await manage_channels(update, context)
    elif data == "manage_users":
        await manage_users(update, context)
    elif data == "stats":
        await show_stats(update, context)
    elif data == "list_banned":
        await list_banned(update, context)
    elif data == "show_channels":
        await show_channels(update, context)
    elif data == "back_start":
        await start(update, context)

# ===================== הפעלת הבוט =====================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler לפרסום
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_receive)],
            BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_confirm, pattern="^confirm_broadcast$")],
        },
        fallbacks=[CallbackQueryHandler(callback_handler)],
    )

    # Conversation handler לערוצים
    channels_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_channel_start, pattern="^add_channel$"),
            CallbackQueryHandler(remove_channel_start, pattern="^remove_channel$"),
        ],
        states={
            ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_receive)],
            REMOVE_CHANNEL: [CallbackQueryHandler(remove_channel_confirm, pattern="^del_channel_")],
        },
        fallbacks=[CallbackQueryHandler(callback_handler)],
    )

    # Conversation handler למשתמשים
    users_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ban_user_start, pattern="^ban_user$"),
            CallbackQueryHandler(unban_user_start, pattern="^unban_user$"),
        ],
        states={
            BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_receive)],
            UNBAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user_receive)],
        },
        fallbacks=[CallbackQueryHandler(callback_handler)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(broadcast_conv)
    app.add_handler(channels_conv)
    app.add_handler(users_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("🤖 הבוט פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
