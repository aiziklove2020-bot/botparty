import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8584994045:AAEj-L74fwHLv7M9M7yE5v4i65SuWJy7Koc"
SUPER_ADMIN = 5508757120
GROUP_ID = -1001371159295

ADMIN_IDS = [SUPER_ADMIN]
APPROVED_PUBLISHERS = []

pending_posts = {}
post_counter = 0
waiting_for = {}


def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_approved(user_id):
    return user_id in APPROVED_PUBLISHERS

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📬 פרסומים ממתינים", callback_data="list_pending")],
        [
            InlineKeyboardButton("👮 ניהול אדמינים", callback_data="manage_admins"),
            InlineKeyboardButton("✅ מפרסמים קבועים", callback_data="manage_publishers"),
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text(
            "🛠 פאנל ניהול - בוט מסיבות בישראל",
            reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(
            "👋 ברוך הבא לבוט מסיבות בישראל!\n\n"
            "📝 שלח לי תמונה או טקסט של המסיבה שלך ואני אשלח אותו לאישור אדמין.\n\n"
            "לאחר האישור הפרסום יועלה לקבוצה 🎉"
        )


async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global post_counter
    user = update.effective_user

    if user.id in waiting_for:
        action = waiting_for.pop(user.id)
        try:
            new_id = int(update.message.text.strip())
        except:
            await update.message.reply_text("❌ ID לא תקין, נסה שוב עם מספר בלבד")
            return

        if action == "add_admin":
            if new_id not in ADMIN_IDS:
                ADMIN_IDS.append(new_id)
                await update.message.reply_text(f"✅ אדמין {new_id} נוסף!")
            else:
                await update.message.reply_text("⚠️ המשתמש כבר אדמין")
        elif action == "add_publisher":
            if new_id not in APPROVED_PUBLISHERS:
                APPROVED_PUBLISHERS.append(new_id)
                await update.message.reply_text(f"✅ מפרסם קבוע {new_id} נוסף!")
            else:
                await update.message.reply_text("⚠️ המשתמש כבר מפרסם קבוע")

        await update.message.reply_text("🛠 פאנל ניהול", reply_markup=main_keyboard())
        return

    if is_approved(user.id):
        try:
            if update.message.photo:
                await context.bot.send_photo(GROUP_ID, update.message.photo[-1].file_id, caption=update.message.caption or "")
            elif update.message.text:
                await context.bot.send_message(GROUP_ID, update.message.text)
            await update.message.reply_text("✅ הפרסום עלה לקבוצה ישירות!")
        except Exception as e:
            await update.message.reply_text(f"❌ שגיאה: {str(e)}")
        return

    post_counter += 1
    post_id = str(post_counter)

    pending_posts[post_id] = {
        "user_id": user.id,
        "user_name": user.full_name,
        "username": user.username,
        "message": update.message,
    }

    await update.message.reply_text("✅ הפרסום שלך נשלח לאישור!\n🙏 תקבל עדכון בקרוב")

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
            if update.message.photo:
                await context.bot.send_photo(admin_id, update.message.photo[-1].file_id, caption=update.message.caption or "")
            elif update.message.text:
                await context.bot.send_message(admin_id, f"📝 תוכן:\n\n{update.message.text}")
            await context.bot.send_message(admin_id, admin_text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error sending to admin {admin_id}: {e}")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.answer("❌ אין לך הרשאה", show_alert=True)
        return

    data = query.data

    if data.startswith("approve_") or data.startswith("reject_"):
        action, post_id = data.split("_", 1)
        post = pending_posts.get(post_id)

        if not post:
            await query.edit_message_text("⚠️ הפרסום כבר טופל")
            return

        if action == "approve":
            try:
                original_msg = post["message"]
                if original_msg.photo:
                    await context.bot.send_photo(GROUP_ID, original_msg.photo[-1].file_id, caption=original_msg.caption or "")
                elif original_msg.text:
                    await context.bot.send_message(GROUP_ID, original_msg.text)
                await query.edit_message_text("✅ הפרסום אושר ופורסם בקבוצה!")
                await context.bot.send_message(post["user_id"], "🎉 הפרסום שלך אושר ופורסם בקבוצה!")
            except Exception as e:
                await query.edit_message_text(f"❌ שגיאה: {str(e)}")

        elif action == "reject":
            await query.edit_message_text("❌ הפרסום נדחה")
            try:
                await context.bot.send_message(
                    post["user_id"],
                    "😔 הפרסום שלך נדחה על ידי האדמין.\n\n"
                    "לפרטים נוספים צור קשר עם המנהל: @aizik_kastoryano"
                )
            except:
                pass

        pending_posts.pop(post_id, None)
        return

    if data == "manage_admins":
        admins_list = "\n".join([f"• {aid} {'👑' if aid == SUPER_ADMIN else ''}" for aid in ADMIN_IDS])
        buttons = [[InlineKeyboardButton("➕ הוסף אדמין", callback_data="add_admin")]]
        for aid in ADMIN_IDS:
            if aid != SUPER_ADMIN:
                buttons.append([InlineKeyboardButton(f"🗑 הסר {aid}", callback_data=f"remove_admin_{aid}")])
        buttons.append([InlineKeyboardButton("🔙 חזור", callback_data="back")])
        await query.edit_message_text(f"👮 אדמינים:\n\n{admins_list}", reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "add_admin":
        waiting_for[user_id] = "add_admin"
        await query.edit_message_text("📝 שלח לי את ה-ID של האדמין החדש:")

    elif data.startswith("remove_admin_"):
        remove_id = int(data.replace("remove_admin_", ""))
        if remove_id == SUPER_ADMIN:
            await query.answer("❌ לא ניתן להסיר את הסופר אדמין", show_alert=True)
            return
        if remove_id in ADMIN_IDS:
            ADMIN_IDS.remove(remove_id)
        await query.edit_message_text(f"✅ אדמין {remove_id} הוסר", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_admins")]]))

    elif data == "manage_publishers":
        pub_list = "\n".join([f"• {pid}" for pid in APPROVED_PUBLISHERS]) if APPROVED_PUBLISHERS else "אין מפרסמים קבועים עדיין"
        buttons = [[InlineKeyboardButton("➕ הוסף מפרסם קבוע", callback_data="add_publisher")]]
        for pid in APPROVED_PUBLISHERS:
            buttons.append([InlineKeyboardButton(f"🗑 הסר {pid}", callback_data=f"remove_publisher_{pid}")])
        buttons.append([InlineKeyboardButton("🔙 חזור", callback_data="back")])
        await query.edit_message_text(f"✅ מפרסמים קבועים:\n\n{pub_list}", reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "add_publisher":
        waiting_for[user_id] = "add_publisher"
        await query.edit_message_text("📝 שלח לי את ה-ID של המפרסם הקבוע החדש:")

    elif data.startswith("remove_publisher_"):
        remove_id = int(data.replace("remove_publisher_", ""))
        if remove_id in APPROVED_PUBLISHERS:
            APPROVED_PUBLISHERS.remove(remove_id)
        await query.edit_message_text(f"✅ מפרסם {remove_id} הוסר", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_publishers")]]))

    elif data == "list_pending":
        count = len(pending_posts)
        await query.edit_message_text(
            f"📬 פרסומים ממתינים: {count}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="back")]])
        )

    elif data == "back":
        await query.edit_message_text("🛠 פאנל ניהול - בוט מסיבות בישראל", reply_markup=main_keyboard())


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_post))
    logger.info("בוט מסיבות פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
