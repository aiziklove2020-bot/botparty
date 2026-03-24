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

# שם + ID של כל אדמין
ADMINS = {
    5508757120: "איציק 👑"
}
APPROVED_PUBLISHERS = {}  # id -> שם

pending_posts = {}
post_counter = 0
waiting_for = {}  # user_id -> action


def is_admin(user_id):
    return user_id in ADMINS

def is_approved(user_id):
    return user_id in APPROVED_PUBLISHERS

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📬 פרסומים ממתינים", callback_data="list_pending")],
        [InlineKeyboardButton("👮 ניהול אדמינים", callback_data="manage_admins")],
        [InlineKeyboardButton("✅ מפרסמים קבועים", callback_data="manage_publishers")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        name = ADMINS.get(user.id, user.full_name)
        await update.message.reply_text(
            f"שלום {name}!\n\n🛠 פאנל ניהול - בוט מסיבות בישראל",
            reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(
            "👋 ברוך הבא לבוט מסיבות בישראל!\n\n"
            "📝 שלח לי תמונה או טקסט של המסיבה שלך ואני אשלח אותו לאישור.\n\n"
            "לאחר האישור הפרסום יועלה לקבוצה 🎉"
        )


async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global post_counter
    user = update.effective_user

    # המתנה להוספת אדמין/מפרסם
    if user.id in waiting_for:
        action = waiting_for.pop(user.id)
        text = update.message.text.strip() if update.message.text else ""

        if action in ("add_admin", "add_publisher"):
            # מצפים ל: "ID שם" או רק ID
            parts = text.split(None, 1)
            try:
                new_id = int(parts[0])
                new_name = parts[1] if len(parts) > 1 else str(new_id)
            except:
                await update.message.reply_text("❌ פורמט לא תקין.\nשלח: `123456789 שם המשתמש`")
                return

            if action == "add_admin":
                if new_id not in ADMINS:
                    ADMINS[new_id] = new_name
                    await update.message.reply_text(f"✅ אדמין {new_name} ({new_id}) נוסף!")
                else:
                    await update.message.reply_text("⚠️ המשתמש כבר אדמין")
            elif action == "add_publisher":
                if new_id not in APPROVED_PUBLISHERS:
                    APPROVED_PUBLISHERS[new_id] = new_name
                    await update.message.reply_text(f"✅ מפרסם קבוע {new_name} ({new_id}) נוסף!")
                else:
                    await update.message.reply_text("⚠️ המשתמש כבר מפרסם קבוע")

        await update.message.reply_text("🛠 פאנל ניהול", reply_markup=main_keyboard())
        return

    # מפרסם קבוע — פרסם ישירות
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

    # משתמש רגיל — שלח לאישור
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
        f"👤 שם: {user.full_name}\n"
        f"🔗 יוזר: @{user.username or 'אין'}\n"
        f"🆔 ID: {user.id}"
    )

    for admin_id in ADMINS:
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

    # אישור/דחייה
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
                await query.edit_message_text("✅ הפרסום אושר ופורסם!")
                await context.bot.send_message(post["user_id"], "🎉 הפרסום שלך אושר ופורסם בקבוצה!")
            except Exception as e:
                await query.edit_message_text(f"❌ שגיאה: {str(e)}")
        elif action == "reject":
            await query.edit_message_text("❌ הפרסום נדחה")
            try:
                await context.bot.send_message(
                    post["user_id"],
                    "😔 הפרסום שלך נדחה.\n\nלפרטים נוספים צור קשר: @aizik_kastoryano"
                )
            except:
                pass
        pending_posts.pop(post_id, None)
        return

    # ניהול אדמינים
    if data == "manage_admins":
        admins_list = "\n".join([f"• {name} ({aid})" for aid, name in ADMINS.items()])
        buttons = [[InlineKeyboardButton("➕ הוסף אדמין", callback_data="add_admin")]]
        for aid, name in ADMINS.items():
            if aid != SUPER_ADMIN:
                buttons.append([InlineKeyboardButton(f"🗑 הסר {name}", callback_data=f"remove_admin_{aid}")])
        buttons.append([InlineKeyboardButton("🔙 חזור", callback_data="back")])
        await query.edit_message_text(f"👮 אדמינים:\n\n{admins_list}", reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "add_admin":
        waiting_for[user_id] = "add_admin"
        await query.edit_message_text("📝 שלח ID ושם:\n\nלדוגמה: `123456789 דני`")

    elif data.startswith("remove_admin_"):
        remove_id = int(data.replace("remove_admin_", ""))
        if remove_id == SUPER_ADMIN:
            await query.answer("❌ לא ניתן להסיר את הסופר אדמין", show_alert=True)
            return
        name = ADMINS.pop(remove_id, remove_id)
        await query.edit_message_text(f"✅ אדמין {name} הוסר", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_admins")]]))

    # ניהול מפרסמים
    elif data == "manage_publishers":
        pub_list = "\n".join([f"• {name} ({pid})" for pid, name in APPROVED_PUBLISHERS.items()]) if APPROVED_PUBLISHERS else "אין מפרסמים קבועים עדיין"
        buttons = [[InlineKeyboardButton("➕ הוסף מפרסם קבוע", callback_data="add_publisher")]]
        for pid, name in APPROVED_PUBLISHERS.items():
            buttons.append([InlineKeyboardButton(f"🗑 הסר {name}", callback_data=f"remove_publisher_{pid}")])
        buttons.append([InlineKeyboardButton("🔙 חזור", callback_data="back")])
        await query.edit_message_text(f"✅ מפרסמים קבועים:\n\n{pub_list}", reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "add_publisher":
        waiting_for[user_id] = "add_publisher"
        await query.edit_message_text("📝 שלח ID ושם:\n\nלדוגמה: `123456789 דני`")

    elif data.startswith("remove_publisher_"):
        remove_id = int(data.replace("remove_publisher_", ""))
        name = APPROVED_PUBLISHERS.pop(remove_id, remove_id)
        await query.edit_message_text(f"✅ מפרסם {name} הוסר", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_publishers")]]))

    elif data == "list_pending":
        count = len(pending_posts)
        await query.edit_message_text(
            f"📬 פרסומים ממתינים: {count}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="back")]])
        )

    elif data == "back":
        name = ADMINS.get(user_id, "")
        await query.edit_message_text(
            f"שלום {name}!\n\n🛠 פאנל ניהול - בוט מסיבות בישראל",
            reply_markup=main_keyboard()
        )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_post))
    logger.info("בוט מסיבות פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
