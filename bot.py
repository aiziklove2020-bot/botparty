import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from config import BOT_TOKEN, ADMIN_IDS
from database import Database

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BROADCAST_MESSAGE, BROADCAST_CONFIRM = range(2)
ADD_CHANNEL, REMOVE_CHANNEL = range(2, 4)
BAN_USER, UNBAN_USER = range(4, 6)
(EVENT_NAME, EVENT_DJ, EVENT_LOCATION, EVENT_DATE, EVENT_LINK, EVENT_FLYER, EVENT_CONFIRM) = range(6, 13)

db = Database()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username or "", user.first_name or "")
    if is_admin(user.id):
        await show_admin_panel(update, context)
    else:
        keyboard = [[InlineKeyboardButton("📢 ערוצים וקבוצות", callback_data="show_channels")]]
        await update.message.reply_text(
            f"👋 שלום {user.first_name}!\nברוך הבא לבוט מסיבות בישראל 🎉",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎉 פרסום אירוע", callback_data="event_publish"),
         InlineKeyboardButton("📢 פרסום חופשי", callback_data="broadcast")],
        [InlineKeyboardButton("📋 ניהול ערוצים", callback_data="manage_channels"),
         InlineKeyboardButton("👥 ניהול משתמשים", callback_data="manage_users")],
        [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")],
    ]
    text = "🛠 *פאנל ניהול אדמין — מסיבות בישראל*\n\nבחר פעולה:"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ===== פרסום אירוע =====

async def event_publish_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['event'] = {}
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="admin_panel")]]
    await query.edit_message_text(
        "🎉 *פרסום אירוע חדש*\n\n*שלב 1/6* — מה *שם האירוע*?\n\nלדוגמה: `TECHNO NIGHT TEL AVIV`",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return EVENT_NAME

async def event_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event']['name'] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("⏭ דלג", callback_data="skip_dj")]]
    await update.message.reply_text(
        "🎧 *שלב 2/6* — מי ה-*DJ/ים*?\n\nלדוגמה: `Shlomi Aber`",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return EVENT_DJ

async def event_dj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event']['dj'] = update.message.text.strip()
    await update.message.reply_text("📍 *שלב 3/6* — *מיקום*\n\nלדוגמה: `The Block, תל אביב`", parse_mode="Markdown")
    return EVENT_LOCATION

async def event_skip_dj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['event']['dj'] = None
    await query.edit_message_text("📍 *שלב 3/6* — *מיקום*\n\nלדוגמה: `The Block, תל אביב`", parse_mode="Markdown")
    return EVENT_LOCATION

async def event_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event']['location'] = update.message.text.strip()
    await update.message.reply_text("📅 *שלב 4/6* — *תאריך ושעה*\n\nלדוגמה: `שישי 21.03 | 23:00`", parse_mode="Markdown")
    return EVENT_DATE

async def event_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event']['date'] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("⏭ דלג", callback_data="skip_link")]]
    await update.message.reply_text(
        "🔗 *שלב 5/6* — *לינק לכרטיסים*\n\nאם אין — לחץ דלג",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return EVENT_LINK

async def event_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['event']['link'] = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("⏭ דלג (ללא פליייר)", callback_data="skip_flyer")]]
    await update.message.reply_text(
        "📸 *שלב 6/6* — שלח *פליייר/תמונה*\n\nאו לחץ דלג",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return EVENT_FLYER

async def event_skip_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['event']['link'] = None
    keyboard = [[InlineKeyboardButton("⏭ דלג (ללא פליייר)", callback_data="skip_flyer")]]
    await query.edit_message_text(
        "📸 *שלב 6/6* — שלח *פליייר/תמונה*\n\nאו לחץ דלג",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return EVENT_FLYER

async def event_flyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['event']['flyer'] = update.message.photo[-1].file_id
    else:
        context.user_data['event']['flyer'] = None
    await show_event_preview(update, context)
    return EVENT_CONFIRM

async def event_skip_flyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['event']['flyer'] = None
    await show_event_preview_query(query, context)
    return EVENT_CONFIRM

def build_event_text(event: dict) -> str:
    lines = ["🎉 *אירוע חדש — מסיבות בישראל* 🎉", "", f"🎪 *{event['name']}*", ""]
    if event.get('dj'):
        lines.append(f"🎧 *DJ:* {event['dj']}")
    lines.append(f"📍 *מיקום:* {event['location']}")
    lines.append(f"📅 *מתי:* {event['date']}")
    if event.get('link'):
        lines.append(f"🎟 *כרטיסים:* {event['link']}")
    lines += ["", "🔥 *מסיבות בישראל* — הקהילה שלנו מחכה לך!"]
    return "\n".join(lines)

async def show_event_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = context.user_data['event']
    text = build_event_text(event)
    channels = db.get_channels()
    channels_text = "\n".join([f"• {ch['name']}" for ch in channels]) if channels else "• אין ערוצים"
    keyboard = [[InlineKeyboardButton("✅ פרסם עכשיו!", callback_data="confirm_event"),
                 InlineKeyboardButton("❌ ביטול", callback_data="admin_panel")]]
    preview = f"👁 *תצוגה מקדימה:*\n\n{text}\n\n📊 ישלח ל:\n{channels_text}\n👥 {db.get_users_count()} משתמשים"
    if event.get('flyer'):
        await update.message.reply_photo(event['flyer'], caption=preview, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(preview, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_event_preview_query(query, context: ContextTypes.DEFAULT_TYPE):
    event = context.user_data['event']
    text = build_event_text(event)
    channels = db.get_channels()
    channels_text = "\n".join([f"• {ch['name']}" for ch in channels]) if channels else "• אין ערוצים"
    keyboard = [[InlineKeyboardButton("✅ פרסם עכשיו!", callback_data="confirm_event"),
                 InlineKeyboardButton("❌ ביטול", callback_data="admin_panel")]]
    preview = f"👁 *תצוגה מקדימה:*\n\n{text}\n\n📊 ישלח ל:\n{channels_text}\n👥 {db.get_users_count()} משתמשים"
    await query.edit_message_text(preview, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def event_confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event = context.user_data.get('event', {})
    text = build_event_text(event)
    success, failed = 0, 0
    for channel in db.get_channels():
        try:
            if event.get('flyer'):
                await context.bot.send_photo(channel['chat_id'], event['flyer'], caption=text, parse_mode="Markdown")
            else:
                await context.bot.send_message(channel['chat_id'], text, parse_mode="Markdown")
            success += 1
        except Exception as e:
            logger.error(f"Channel error: {e}")
            failed += 1
    for user in db.get_all_users():
        try:
            if event.get('flyer'):
                await context.bot.send_photo(user['user_id'], event['flyer'], caption=text, parse_mode="Markdown")
            else:
                await context.bot.send_message(user['user_id'], text, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await query.edit_message_text(f"✅ *האירוע פורסם!*\n\n✔️ {success}\n❌ {failed}", parse_mode="Markdown")
    return ConversationHandler.END

# ===== פרסום חופשי =====

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="admin_panel")]]
    await query.edit_message_text("📢 *פרסום חופשי*\n\nשלח הודעה, תמונה או וידאו:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return BROADCAST_MESSAGE

async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_msg'] = update.message
    channels = db.get_channels()
    channels_text = "\n".join([f"• {ch['name']}" for ch in channels]) if channels else "• אין ערוצים"
    keyboard = [[InlineKeyboardButton("✅ אשר", callback_data="confirm_broadcast"),
                 InlineKeyboardButton("❌ ביטול", callback_data="admin_panel")]]
    await update.message.reply_text(
        f"📋 ישלח ל:\n{channels_text}\n👥 {db.get_users_count()} משתמשים\n\nלשלוח?",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg = context.user_data.get('broadcast_msg')
    success, failed = 0, 0
    for channel in db.get_channels():
        try:
            if msg.photo:
                await context.bot.send_photo(channel['chat_id'], msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await context.bot.send_video(channel['chat_id'], msg.video.file_id, caption=msg.caption)
            else:
                await context.bot.send_message(channel['chat_id'], msg.text)
            success += 1
        except:
            failed += 1
    for user in db.get_all_users():
        try:
            if msg.photo:
                await context.bot.send_photo(user['user_id'], msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await context.bot.send_video(user['user_id'], msg.video.file_id, caption=msg.caption)
            else:
                await context.bot.send_message(user['user_id'], msg.text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await query.edit_message_text(f"✅ *הושלם!*\n✔️ {success} | ❌ {failed}", parse_mode="Markdown")
    return ConversationHandler.END

# ===== ניהול ערוצים =====

async def manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get_channels()
    channels_text = "\n".join([f"• {ch['name']}" for ch in channels]) if channels else "אין ערוצים"
    keyboard = [
        [InlineKeyboardButton("➕ הוסף", callback_data="add_channel"),
         InlineKeyboardButton("➖ הסר", callback_data="remove_channel")],
        [InlineKeyboardButton("🔙 חזור", callback_data="admin_panel")]
    ]
    await query.edit_message_text(f"📋 *ניהול ערוצים*\n\n{channels_text}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="manage_channels")]]
    await query.edit_message_text("➕ שלח Chat ID של הערוץ/קבוצה:\n\nלמצוא: הוסף `@userinfobot` לערוץ", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ADD_CHANNEL

async def add_channel_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = int(update.message.text.strip())
        chat = await context.bot.get_chat(chat_id)
        db.add_channel(chat_id, chat.title or str(chat_id))
        await update.message.reply_text(f"✅ *{chat.title}* נוסף!", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ ID לא תקין.")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {str(e)}")
    return ConversationHandler.END

async def remove_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get_channels()
    if not channels:
        await query.edit_message_text("אין ערוצים.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_channels")]]))
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
    await query.edit_message_text("✅ הוסר!")
    return ConversationHandler.END

# ===== ניהול משתמשים =====

async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🚫 חסום", callback_data="ban_user"),
         InlineKeyboardButton("✅ שחרר", callback_data="unban_user")],
        [InlineKeyboardButton("📋 רשימת חסומים", callback_data="list_banned")],
        [InlineKeyboardButton("🔙 חזור", callback_data="admin_panel")]
    ]
    await query.edit_message_text(
        f"👥 *משתמשים*\n\n👤 {db.get_users_count()}\n🚫 {db.get_banned_count()} חסומים",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

async def ban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚫 שלח User ID לחסימה:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ביטול", callback_data="manage_users")]]))
    return BAN_USER

async def ban_user_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text.strip())
        db.ban_user(user_id)
        await update.message.reply_text(f"✅ `{user_id}` נחסם.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ ID לא תקין.")
    return ConversationHandler.END

async def unban_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ שלח User ID לשחרור:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ביטול", callback_data="manage_users")]]))
    return UNBAN_USER

async def unban_user_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text.strip())
        db.unban_user(user_id)
        await update.message.reply_text(f"✅ `{user_id}` שוחרר.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ ID לא תקין.")
    return ConversationHandler.END

async def list_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    banned = db.get_banned_users()
    text = "🚫 *חסומים:*\n\n" + "\n".join([f"• `{u['user_id']}`" for u in banned]) if banned else "✅ אין חסומים."
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_users")]]), parse_mode="Markdown")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"📊 *סטטיסטיקות*\n\n👤 {db.get_users_count()} משתמשים\n📢 {len(db.get_channels())} ערוצים\n🚫 {db.get_banned_count()} חסומים",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="admin_panel")]]),
        parse_mode="Markdown"
    )

async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channels = db.get_channels()
    if not channels:
        await query.edit_message_text("אין ערוצים עדיין.")
        return
    keyboard = [[InlineKeyboardButton(f"📢 {ch['name']}", url=f"https://t.me/{ch.get('username','')}")] for ch in channels if ch.get('username')]
    keyboard.append([InlineKeyboardButton("🔙 חזור", callback_data="back_start")])
    await query.edit_message_text("📢 *הערוצים שלנו:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
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

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    event_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(event_publish_start, pattern="^event_publish$")],
        states={
            EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_name)],
            EVENT_DJ: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_dj), CallbackQueryHandler(event_skip_dj, pattern="^skip_dj$")],
            EVENT_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_location)],
            EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_date)],
            EVENT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_link), CallbackQueryHandler(event_skip_link, pattern="^skip_link$")],
            EVENT_FLYER: [MessageHandler(filters.PHOTO, event_flyer), CallbackQueryHandler(event_skip_flyer, pattern="^skip_flyer$")],
            EVENT_CONFIRM: [CallbackQueryHandler(event_confirm_send, pattern="^confirm_event$")],
        },
        fallbacks=[CallbackQueryHandler(callback_handler)],
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, pattern="^broadcast$")],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_receive)],
            BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_confirm, pattern="^confirm_broadcast$")],
        },
        fallbacks=[CallbackQueryHandler(callback_handler)],
    )

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
    app.add_handler(event_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(channels_conv)
    app.add_handler(users_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("🤖 הבוט פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
