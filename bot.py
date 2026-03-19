import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from config import BOT_TOKEN, ADMIN_IDS, CHANNEL_ID

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

SUBMIT_TEXT, SUBMIT_PHOTO = range(2)
REJECT_REASON = 10
ADD_ADMIN = 20
REMOVE_ADMIN = 21

def init_db():
    conn = sqlite3.connect("posts.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS pending_posts (
        post_id TEXT PRIMARY KEY,
        user_id INTEGER,
        username TEXT,
        text TEXT,
        photo_id TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        added_by INTEGER
    )""")
    conn.commit()
    conn.close()

def get_all_admins():
    conn = sqlite3.connect("posts.db")
    rows = conn.execute("SELECT * FROM admins").fetchall()
    conn.close()
    return [{"user_id": r[0], "username": r[1], "added_by": r[2]} for r in rows]

def add_admin_db(user_id, username, added_by):
    conn = sqlite3.connect("posts.db")
    conn.execute("INSERT OR REPLACE INTO admins VALUES (?,?,?)", (user_id, username, added_by))
    conn.commit()
    conn.close()

def remove_admin_db(user_id):
    conn = sqlite3.connect("posts.db")
    conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def save_post(post_id, user_id, username, text, photo_id):
    conn = sqlite3.connect("posts.db")
    conn.execute("INSERT OR REPLACE INTO pending_posts VALUES (?,?,?,?,?)",
                 (post_id, user_id, username, text, photo_id))
    conn.commit()
    conn.close()

def get_all_posts():
    conn = sqlite3.connect("posts.db")
    rows = conn.execute("SELECT * FROM pending_posts").fetchall()
    conn.close()
    return [{"post_id": r[0], "user_id": r[1], "username": r[2], "text": r[3], "photo": r[4]} for r in rows]

def get_post(post_id):
    conn = sqlite3.connect("posts.db")
    r = conn.execute("SELECT * FROM pending_posts WHERE post_id=?", (post_id,)).fetchone()
    conn.close()
    if r:
        return {"post_id": r[0], "user_id": r[1], "username": r[2], "text": r[3], "photo": r[4]}
    return None

def delete_post(post_id):
    conn = sqlite3.connect("posts.db")
    conn.execute("DELETE FROM pending_posts WHERE post_id=?", (post_id,))
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id in ADMIN_IDS:
        return True
    conn = sqlite3.connect("posts.db")
    r = conn.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return r is not None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")],
            [InlineKeyboardButton("📋 ממתינים לאישור", callback_data="pending_list")],
            [InlineKeyboardButton("👥 ניהול מנהלים", callback_data="manage_admins")] if user.id in ADMIN_IDS else [],
        ]
        keyboard = [row for row in keyboard if row]
        await update.message.reply_text(
            "👋 שלום " + user.first_name + "!\n\n🛠 פאנל אדמין - מסיבות בישראל",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        keyboard = [[InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")]]
        await update.message.reply_text(
            "👋 שלום " + user.first_name + "!\n\nברוך הבא לבוט מסיבות בישראל 🎉\n\nרוצה לפרסם מסיבה? לחץ כאן 👇",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def submit_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="cancel")]]
    await query.edit_message_text(
        "🎉 שליחת מסיבה לפרסום\n\nשלח את תיאור המסיבה:\n\nכתוב הכל במסר אחד:\n- שם המסיבה\n- תאריך ושעה\n- מיקום\n- DJ / אמנים\n- כל פרט שתרצה",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SUBMIT_TEXT

async def submit_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["post_text"] = update.message.text
    keyboard = [[InlineKeyboardButton("⏭ דלג (ללא תמונה)", callback_data="skip_photo")]]
    await update.message.reply_text(
        "📸 שלח פליייר/תמונה\n\nאו לחץ דלג",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SUBMIT_PHOTO

async def submit_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["post_photo"] = update.message.photo[-1].file_id
    user = update.effective_user
    post_id = str(user.id) + "_" + str(update.message.message_id)
    await _save_and_notify(context, post_id, user, context.user_data["post_text"], context.user_data["post_photo"])
    await update.message.reply_text("✅ הפרסום שלך נשלח לאישור!\n\nתקבל עדכון בקרוב 🙏")
    return ConversationHandler.END

async def submit_skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    post_id = str(user.id) + "_" + str(query.message.message_id)
    await _save_and_notify(context, post_id, user, context.user_data["post_text"], None)
    await query.edit_message_text("✅ הפרסום שלך נשלח לאישור!\n\nתקבל עדכון בקרוב 🙏")
    return ConversationHandler.END

async def _save_and_notify(context, post_id, user, text, photo):
    username = user.username if user.username else user.first_name
    save_post(post_id, user.id, username, text, photo)
    keyboard = [
        [InlineKeyboardButton("✅ אשר ופרסם", callback_data="approve_" + post_id),
         InlineKeyboardButton("❌ דחה", callback_data="reject_" + post_id)]
    ]
    admin_text = "🔔 פרסום חדש ממתין לאישור!\n\n👤 שולח: @" + username + " (" + str(user.id) + ")\n\n📝 תוכן:\n" + text
    for admin_id in ADMIN_IDS:
        try:
            if photo:
                await context.bot.send_photo(admin_id, photo, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await context.bot.send_message(admin_id, admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error("Admin notify error: " + str(e))

async def approve_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post_id = query.data.replace("approve_", "")
    post = get_post(post_id)
    if not post:
        await query.answer("❌ הפרסום לא נמצא או כבר טופל.", show_alert=True)
        return
    try:
        channel_text = "🎉 מסיבות בישראל\n\n" + post["text"]
        if post["photo"]:
            await context.bot.send_photo(CHANNEL_ID, post["photo"], caption=channel_text)
        else:
            await context.bot.send_message(CHANNEL_ID, channel_text)
        try:
            if post["photo"]:
                await query.edit_message_caption("✅ אושר ופורסם בערוץ!")
            else:
                await query.edit_message_text("✅ אושר ופורסם בערוץ!")
        except:
            pass
        await context.bot.send_message(post["user_id"], "🎉 הפרסום שלך אושר ופורסם בערוץ!\n\nתודה 🙏")
    except Exception as e:
        await context.bot.send_message(query.from_user.id, "❌ שגיאה: " + str(e))
    delete_post(post_id)

async def reject_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    post_id = query.data.replace("reject_", "")
    post = get_post(post_id)
    if not post:
        await query.answer("❌ הפרסום לא נמצא.", show_alert=True)
        return
    context.user_data["rejecting_post_id"] = post_id
    keyboard = [
        [InlineKeyboardButton("🌊 הצפת ערוץ", callback_data="reason_flood")],
        [InlineKeyboardButton("🚫 לא מתאים לתוכן", callback_data="reason_content")],
        [InlineKeyboardButton("📅 כפול / כבר פורסם", callback_data="reason_duplicate")],
        [InlineKeyboardButton("📝 חסר פרטים", callback_data="reason_missing")],
        [InlineKeyboardButton("✏️ סיבה אחרת", callback_data="reason_custom")],
    ]
    try:
        if post["photo"]:
            await query.edit_message_caption("❌ בחר סיבת דחייה:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ בחר סיבת דחייה:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error("Reject error: " + str(e))

async def reject_with_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reasons = {
        "reason_flood": "הערוץ מוגבל כרגע בכמות הפרסומים - נסה שוב מאוחר יותר 🌊",
        "reason_content": "הפרסום אינו מתאים לתוכן הערוץ 🚫",
        "reason_duplicate": "פרסום זהה כבר קיים בערוץ 📅",
        "reason_missing": "הפרסום חסר פרטים - אנא השלם ושלח מחדש 📝",
    }
    reason_key = query.data
    post_id = context.user_data.get("rejecting_post_id")
    post = get_post(post_id)
    if reason_key == "reason_custom":
        await query.edit_message_text("✏️ כתוב את סיבת הדחייה:")
        return REJECT_REASON
    if not post:
        return ConversationHandler.END
    await _send_rejection(context, post, post_id, reasons[reason_key], query)
    return ConversationHandler.END

async def reject_custom_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_id = context.user_data.get("rejecting_post_id")
    post = get_post(post_id)
    if post:
        await _send_rejection(context, post, post_id, update.message.text.strip(), None)
        await update.message.reply_text("✅ הדחייה נשלחה.")
    return ConversationHandler.END

async def _send_rejection(context, post, post_id, reason, query):
    try:
        await context.bot.send_message(
            post["user_id"],
            "❌ הפרסום שלך לא אושר\n\nסיבה: " + reason + "\n\nאתה מוזמן לתקן ולשלוח מחדש 🙏"
        )
    except Exception as e:
        logger.error("Reject notify error: " + str(e))
    if query:
        try:
            if post["photo"]:
                await query.edit_message_caption("❌ נדחה\nסיבה: " + reason)
            else:
                await query.edit_message_text("❌ נדחה\nסיבה: " + reason)
        except:
            pass
    delete_post(post_id)

async def pending_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    posts = get_all_posts()
    if not posts:
        await query.edit_message_text(
            "✅ אין פרסומים ממתינים",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="back_start")]])
        )
        return
    await query.edit_message_text("📋 " + str(len(posts)) + " פרסומים ממתינים:")
    for post in posts:
        keyboard = [
            [InlineKeyboardButton("✅ אשר ופרסם", callback_data="approve_" + post["post_id"]),
             InlineKeyboardButton("❌ דחה", callback_data="reject_" + post["post_id"])]
        ]
        admin_text = "🔔 ממתין לאישור\n\n👤 @" + post["username"] + " (" + str(post["user_id"]) + ")\n\n📝 " + post["text"]
        try:
            if post["photo"]:
                await context.bot.send_photo(query.from_user.id, post["photo"], caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await context.bot.send_message(query.from_user.id, admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error("Pending list error: " + str(e))


async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    admins = get_all_admins()
    admins_text = "\n".join(["- @" + a["username"] + " (" + str(a["user_id"]) + ")" for a in admins]) if admins else "אין מנהלים נוספים"
    keyboard = [
        [InlineKeyboardButton("➕ הוסף מנהל", callback_data="add_admin")],
        [InlineKeyboardButton("➖ הסר מנהל", callback_data="remove_admin")],
        [InlineKeyboardButton("🔙 חזור", callback_data="back_start")],
    ]
    await query.edit_message_text(
        "👥 ניהול מנהלים\n\nמנהלים נוספים:\n" + admins_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ ביטול", callback_data="manage_admins")]]
    await query.edit_message_text(
        "➕ הוספת מנהל\n\nשלח את ה-User ID של המנהל החדש\n\nאיך מוצאים ID: שלח הודעה ל-@userinfobot",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADD_ADMIN

async def add_admin_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        new_admin_id = int(update.message.text.strip())
        if new_admin_id in ADMIN_IDS:
            await update.message.reply_text("⚠️ המשתמש כבר מנהל ראשי.")
            return ConversationHandler.END
        try:
            chat = await context.bot.get_chat(new_admin_id)
            username = chat.username or chat.first_name or str(new_admin_id)
        except:
            username = str(new_admin_id)
        add_admin_db(new_admin_id, username, update.effective_user.id)
        await update.message.reply_text("✅ @" + username + " נוסף כמנהל!")
        try:
            await context.bot.send_message(new_admin_id, "🎉 נוספת כמנהל בבוט מסיבות בישראל!\n\nשלח /start כדי להתחיל.")
        except:
            pass
    except ValueError:
        await update.message.reply_text("❌ ID לא תקין. שלח מספר בלבד.")
    return ConversationHandler.END

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admins = get_all_admins()
    if not admins:
        await query.edit_message_text(
            "אין מנהלים נוספים להסרה.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="manage_admins")]])
        )
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton("🗑 @" + a["username"], callback_data="del_admin_" + str(a["user_id"]))] for a in admins]
    keyboard.append([InlineKeyboardButton("❌ ביטול", callback_data="manage_admins")])
    await query.edit_message_text("בחר מנהל להסרה:", reply_markup=InlineKeyboardMarkup(keyboard))
    return REMOVE_ADMIN

async def remove_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = int(query.data.replace("del_admin_", ""))
    remove_admin_db(admin_id)
    await query.edit_message_text("✅ המנהל הוסר!")
    try:
        await context.bot.send_message(admin_id, "❌ הוסרת מרשימת המנהלים בבוט מסיבות בישראל.")
    except:
        pass
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")]]
    await query.edit_message_text("בוטל.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "pending_list":
        await pending_list(update, context)
    elif data == "back_start":
        await update.callback_query.answer()
        user = update.effective_user
        if is_admin(user.id):
            keyboard = [[InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")], [InlineKeyboardButton("📋 ממתינים לאישור", callback_data="pending_list")]]
        else:
            keyboard = [[InlineKeyboardButton("🎉 שלח מסיבה לפרסום", callback_data="submit_post")]]
        await update.callback_query.edit_message_text("בחר פעולה:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("approve_"):
        await approve_post(update, context)
    elif data == "manage_admins":
        await manage_admins(update, context)
    elif data == "add_admin":
        await add_admin_start(update, context)
    elif data == "remove_admin":
        await remove_admin_start(update, context)

def main():
    init_db()
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

    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_admin_start, pattern="^add_admin$"),
            CallbackQueryHandler(remove_admin_start, pattern="^remove_admin$"),
        ],
        states={
            ADD_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_receive)],
            REMOVE_ADMIN: [CallbackQueryHandler(remove_admin_confirm, pattern="^del_admin_")],
        },
        fallbacks=[CallbackQueryHandler(manage_admins, pattern="^manage_admins$")],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(submit_conv)
    app.add_handler(reject_conv)
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("הבוט פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
