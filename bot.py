import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8584994045:AAEj-L74fwHLv7M9M7yE5v4i65SuWJy7Koc"
ADMIN_IDS = [5508757120]
GROUP_ID = -1001371159295

# שמירת פרסומים ממתינים בזיכרון
pending_posts = {}
post_counter = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ברוך הבא לבוט מסיבות בישראל!\n\n"
        "📝 שלח לי תמונה או טקסט של המסיבה שלך ואני אשלח אותו לאישור אדמין.\n\n"
        "לאחר האישור הפרסום יועלה לקבוצה 🎉"
    )

async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global post_counter
    user = update.effective_user

    post_counter += 1
    post_id = str(post_counter)

    # שמירת הפרסום
    pending_posts[post_id] = {
        "user_id": user.id,
        "user_name": user.full_name,
        "username": user.username,
        "message": update.message,
        "chat_id": update.effective_chat.id
    }

    # אישור למשתמש
    await update.message.reply_text(
        "✅ הפרסום שלך נשלח לאישור!\n"
        "🙏 תקבל עדכון בקרוב"
    )

    # שליחה לכל אדמין
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ אשר", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton("❌ דחה", callback_data=f"reject_{post_id}")
        ]
    ])

    admin_text = (
        f"📬 פרסום חדש ממתין לאישור\n\n"
        f"👤 משתמש: {user.full_name}\n"
        f"🔗 יוזר: @{user.username or 'אין'}\n"
        f"🆔 ID: {user.id}\n\n"
        f"האם לאשר את הפרסום?"
    )

    for admin_id in ADMIN_IDS:
        try:
            # שליחת ההודעה המקורית לאדמין
            if update.message.photo:
                await context.bot.send_photo(
                    admin_id,
                    update.message.photo[-1].file_id,
                    caption=update.message.caption or ""
                )
            elif update.message.text:
                await context.bot.send_message(admin_id, f"📝 תוכן:\n\n{update.message.text}")

            await context.bot.send_message(admin_id, admin_text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error sending to admin: {e}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ אין לך הרשאה", show_alert=True)
        return

    data = query.data
    action, post_id = data.split("_", 1)
    post = pending_posts.get(post_id)

    if not post:
        await query.edit_message_text("⚠️ הפרסום כבר טופל או לא נמצא")
        return

    if action == "approve":
        try:
            original_msg = post["message"]
            # פרסום לקבוצה
            if original_msg.photo:
                await context.bot.send_photo(
                    GROUP_ID,
                    original_msg.photo[-1].file_id,
                    caption=original_msg.caption or ""
                )
            elif original_msg.text:
                await context.bot.send_message(GROUP_ID, original_msg.text)

            # עדכון אדמין
            await query.edit_message_text(f"✅ הפרסום אושר ופורסם בקבוצה!")

            # עדכון משתמש
            await context.bot.send_message(
                post["user_id"],
                "🎉 הפרסום שלך אושר ופורסם בקבוצה!"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ שגיאה בפרסום: {str(e)}")

    elif action == "reject":
        await query.edit_message_text(f"❌ הפרסום נדחה")
        try:
            await context.bot.send_message(
                post["user_id"],
                "😔 הפרסום שלך נדחה על ידי האדמין"
            )
        except:
            pass

    # מחיקה מהרשימה
    pending_posts.pop(post_id, None)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return

    pending_count = len(pending_posts)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📋 פרסומים ממתינים ({pending_count})", callback_data="list_pending")]
    ])
    await update.message.reply_text(
        "🛠 פאנל אדמין - בוט מסיבות\n\n"
        f"📬 פרסומים ממתינים: {pending_count}",
        reply_markup=keyboard
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_post))
    logger.info("בוט מסיבות פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
