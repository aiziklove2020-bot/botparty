import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from config import BOT_TOKEN, ADMIN_IDS, CHANNEL_ID

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SUBMIT_TEXT, SUBMIT_PHOTO = range(2)
REJECT_REASON = 10

pending_posts = {}
rejecting = {}  # שמירת post_id שנדחה בזמן הקלדת סיבה

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ===================== START =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("📢 פרסם מסיבה", callback_data="submit_post")],
            [InlineKeyboardButton("📋 ממתינים לאישור", callback_data="pending_list")],
        ]
        await update.message.reply_text(
            f"👋 שלום {user.first_name}!\n\n🛠 *פאנל אדמין — מסיבות בישראל*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        keyboard = [[InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")]]
        await update.message.reply_text(
            f"👋 שלום {user.first_name}!\n\n"
            f"ברוך הבא לבוט *מסיבות בישראל* 🎉\n\n"
            f"רוצה לפרסם מסיבה? לחץ כאן 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# ===================== שליחת מסיבה =====================

async def submit_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="cancel")]]
    await query.edit_message_text(
        "🎉 *שליחת מסיבה לפרסום*\n\n"
        "*שלב 1/2* — שלח את *תיאור המסיבה*:\n\n"
        "כתוב הכל במסר אחד:\n"
        "• שם המסיבה\n"
        "• תאריך ושעה\n"
        "• מיקום\n"
        "• DJ / אמנים\n"
        "• כל פרט שתרצה",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SUBMIT_TEXT

async def submit_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['post_text'] = update.message.text
    keyboard = [[InlineKeyboardButton("⏭ דלג (ללא תמונה)", callback_data="skip_photo")]]
    await update.message.reply_text(
        "📸 *שלב 2/2* — שלח *פליייר/תמונה*\n\n_או לחץ דלג_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return SUBMIT_PHOTO

async def submit_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['post_photo'] = update.message.photo[-1].file_id
    await send_for_approval(update, context)
    return ConversationHandler.END

async def submit_skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['post_photo'] = None
    await send_for_approval_query(query, context)
    return ConversationHandler.END

async def send_for_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = context.user_data.get('post_text', '')
    photo = context.user_data.get('post_photo')
    post_id = f"{user.id}_{update.message.message_id}"
    pending_posts[post_id] = {'user_id': user.id, 'username': user.username or user.first_name, 'text': text, 'photo': photo}
    await _notify_admins(context, post_id, user, text, photo)
    await update.message.reply_text("✅ *הפרסום שלך נשלח לאישור!*\n\nתקבל עדכון בקרוב 🙏", parse_mode="Markdown")

async def send_for_approval_query(query, context: ContextTypes.DEFAULT_TYPE):
    user = query.from_user
    text = context.user_data.get('post_text', '')
    photo = context.user_data.get('post_photo')
    post_id = f"{user.id}_{query.message.message_id}"
    pending_posts[post_id] = {'user_id': user.id, 'username': user.username or user.first_name, 'text': text, 'photo': photo}
    await _notify_admins(context, post_id, user, text, photo)
    await query.edit_message_text("✅ *הפרסום שלך נשלח לאישור!*\n\nתקבל עדכון בקרוב 🙏", parse_mode="Markdown")

async def _notify_admins(context, post_id, user, text, photo):
    keyboard = [
        [InlineKeyboardButton("✅ אשר ופרסם", callback_data=f"approve_{post_id}"),
         InlineKeyboardButton("❌ דחה", callback_data=f"reject_{post_id}")]
    ]
    admin_text = (
        f"🔔 *פרסום חדש ממתין לאישור!*\n\n"
        f"👤 שולח: @{user.username or user.first_name} (`{user.id}`)\n\n"
        f"📝 *תוכן:*\n{text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            if photo:
                await context.bot.send_photo(admin_id, photo, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await context.bot.send_message(admin_id, admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

# ===================== אישור =====================

async def approve_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post_id = query.data.replace("approve_", "")
    post = pending_posts.get(post_id)
    if not post:
        await query.answer("❌ הפרסום לא נמצא או כבר טופל.", show_alert=True)
        return
    text = post['text']
    photo = post['photo']
    try:
        if photo:
            await context.bot.send_photo(CHANNEL_ID, photo, caption=f"🎉 *מסיבות בישראל*\n\n{text}", parse_mode="Markdown")
        else:
            await context.bot.send_message(CHANNEL_ID, f"🎉 *מסיבות בישראל*\n\n{text}", parse_mode="Markdown")

        if photo:
            await query.edit_message_caption(f"✅ *אושר ופורסם בערוץ!*", parse_mode="Markdown")
        else:
            await query.edit_message_text(f"✅ *אושר ופורסם בערוץ!*", parse_mode="Markdown")

        await context.bot.send_message(post['user_id'], "🎉 *הפרסום שלך אושר ופורסם בערוץ!*\n\nתודה על השיתוף 🙏", parse_mode="Markdown")
    except Exception as e:
        await context.bot.send_message(query.from_user.id, f"❌ שגיאה בפרסום: {str(e)}")
    pending_posts.pop(post_id, None)

# ===================== דחייה עם סיבה =====================

async def reject_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post_id = query.data.replace("reject_", "")
    post = pending_posts.get(post_id)
    if not post:
        await query.answer("❌ הפרסום לא נמצא או כבר טופל.", show_alert=True)
        return

    # שמור post_id לשלב הבא
    context.user_data['rejecting_post_id'] = post_id

    keyboard = [
        [InlineKeyboardButton("🌊 הצפת ערוץ", callback_data="reason_flood")],
        [InlineKeyboardButton("🚫 לא מתאים לתוכן", callback_data="reason_content")],
        [InlineKeyboardButton("📅 כפול / כבר פורסם", callback_data="reason_duplicate")],
        [InlineKeyboardButton("📝 חסר פרטים", callback_data="reason_missing")],
        [InlineKeyboardButton("✏️ סיבה אחרת (כתוב)", callback_data="reason_custom")],
    ]
    try:
        if post.get('photo'):
            await query.edit_message_caption("❌ *בחר סיבת דחייה:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ *בחר סיבת דחייה:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except:
        await query.message.reply_text("❌ *בחר סיבת דחייה:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def reject_with_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    reasons = {
        "reason_flood": "הערוץ מוגבל כרגע בכמות הפרסומים (הצפה) — נסה שוב מאוחר יותר 🌊",
        "reason_content": "הפרסום אינו מתאים לתוכן הערוץ 🚫",
        "reason_duplicate": "פרסום זהה כבר קיים בערוץ 📅",
        "reason_missing": "הפרסום חסר פרטים חשובים — אנא השלם ושלח מחדש 📝",
    }

    reason_key = query.data
    post_id = context.user_data.get('rejecting_post_id')
    post = pending_posts.get(post_id)

    if reason_key == "reason_custom":
        try:
            await query.edit_message_text("✏️ *כתוב את סיבת הדחייה:*", parse_mode="Markdown")
        except:
            await query.message.reply_text("✏️ *כתוב את סיבת הדחייה:*", parse_mode="Markdown")
        return REJECT_REASON

    if not post:
        return ConversationHandler.END

    reason_text = reasons.get(reason_key, "הפרסום נדחה.")
    await _send_rejection(context, post, post_id, reason_text, query)
    return ConversationHandler.END

async def reject_custom_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason_text = update.message.text.strip()
    post_id = context.user_data.get('rejecting_post_id')
    post = pending_posts.get(post_id)
    if post:
        await _send_rejection(context, post, post_id, reason_text, None)
        await update.message.reply_text("✅ הדחייה נשלחה למשתמש.")
    return ConversationHandler.END

async def _send_rejection(context, post, post_id, reason_text, query):
    # הודעה למשתמש
    try:
        await context.bot.send_message(
            post['user_id'],
            f"❌ *הפרסום שלך לא אושר*\n\n"
            f"*סיבה:* {reason_text}\n\n"
            f"אתה מוזמן לתקן ולשלוח מחדש 🙏",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Reject notify error: {e}")

    # עדכון הודעת האדמין
    if query:
        try:
            if post.get('photo'):
                await query.edit_message_caption(f"❌ *נדחה*\nסיבה: {reason_text}", parse_mode="Markdown")
            else:
                await query.edit_message_text(f"❌ *נדחה*\nסיבה: {reason_text}", parse_mode="Markdown")
        except:
            pass

    pending_posts.pop(post_id, None)

# ===================== רשימת ממתינים =====================

async def pending_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not pending_posts:
        await query.edit_message_text("✅ *אין פרסומים ממתינים*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="back_start")]]), parse_mode="Markdown")
        return
    text = f"📋 *{len(pending_posts)} פרסומים ממתינים:*\n\n"
    for pid, p in pending_posts.items():
        text += f"• @{p['username']}: {p['text'][:40]}...\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="back_start")]]), parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")]]
    await query.edit_message_text("בוטל. רוצה לשלוח מסיבה?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "back_start":
        await update.callback_query.answer()
        user = update.effective_user
        keyboard = [[InlineKeyboardButton("📢 פרסם מסיבה", callback_data="submit_post")], [InlineKeyboardButton("📋 ממתינים לאישור", callback_data="pending_list")]] if is_admin(user.id) else [[InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")]]
        await update.callback_query.edit_message_text("🛠 *פאנל אדמין*" if is_admin(user.id) else "ברוך הבא 🎉", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif data == "pending_list":
        await pending_list(update, context)
    elif data.startswith("approve_"):
        await approve_post(update, context)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    submit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_post_start, pattern="^submit_post$")],
        states={
            SUBMIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, submit_text_received)],
            SUBMIT_PHOTO: [
                MessageHandler(filters.PHOTO, submit_photo_received),
                CallbackQueryHandler(submit_skip_photo, pattern="^skip_photo$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$")],
    )

    reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_post, pattern="^reject_")],
        states={
            0: [CallbackQueryHandler(reject_with_reason, pattern="^reason_")],
            REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_custom_reason)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(submit_conv)
    app.add_handler(reject_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("🤖 הבוט פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
