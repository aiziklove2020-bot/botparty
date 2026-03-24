import logging
import asyncio
import random
import os
from datetime import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from groq import Groq

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
ADMIN_IDS = [int(os.environ.get("ADMIN_ID", "5508757120"))]
GROUP_ID = -1002472743528

USED_TOPICS = []

TOPICS_POOL = [
    "גבולות ותקשורת בעולם BDSM",
    "Safe Word - למה זה כל כך חשוב?",
    "ההבדל בין Dom ל-Sub",
    "Aftercare - מה קורה אחרי הסצנה?",
    "איך מתחילים לחקור BDSM בבטחה?",
    "SSC vs RACK - איזה פילוסופיה אתם מאמינים בה?",
    "Trust - איך בונים אמון בין שותפים?",
    "Collaring - מה המשמעות של קולר?",
    "Sub Drop ו-Dom Drop - איך מתמודדים?",
    "Soft Limits vs Hard Limits",
    "Online BDSM - האם זה עובד?",
    "Rope Bondage - אמנות או נשק?",
    "הסכמה - הבסיס של הכל",
    "Public Play - כן או לא?",
    "Switch - להיות גם Dom וגם Sub",
    "Punishment vs Funishment",
    "BDSM ובריאות נפשית",
    "קינקים נפוצים - מה אתם אוהבים?",
    "איך מוצאים שותף BDSM?",
    "Scene Planning - איך מתכננים סצנה?",
    "Power Exchange - מה זה אומר לכם?",
    "Sadomasochism - כאב כעונג",
    "BDSM ויחסים רומנטיים",
    "Fetish - מה ההבדל בין פטיש לקינק?",
]

def generate_discussion_sync():
    global USED_TOPICS
    available = [t for t in TOPICS_POOL if t not in USED_TOPICS]
    if not available:
        USED_TOPICS = []
        available = TOPICS_POOL
    topic = random.choice(available)
    USED_TOPICS.append(topic)

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": (
                    "אתה מנחה קהילת BDSM בישראל. "
                    "צור דיון יומי מעניין בעברית על הנושא: " + topic + "\n\n"
                    "הפורמט:\n"
                    "🔥 נושא הדיון: " + topic + "\n\n"
                    "[2-3 משפטים על הנושא]\n\n"
                    "💬 שאלה לקהילה: [שאלה פתוחה מעניינת]\n\n"
                    "שפה מכבדת ופתוחה. ללא מוסר."
                )
            }
        ],
        max_tokens=400
    )
    return response.choices[0].message.content

async def send_daily_discussion(context: ContextTypes.DEFAULT_TYPE):
    try:
        loop = asyncio.get_event_loop()
        discussion = await loop.run_in_executor(None, generate_discussion_sync)
        await context.bot.send_message(GROUP_ID, discussion)
        logger.info("Daily discussion sent!")
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, "✅ הדיון היומי נשלח!")
            except:
                pass
    except Exception as e:
        logger.error("Error: " + str(e))
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(admin_id, "❌ שגיאה: " + str(e))
            except:
                pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("👋 הבוט שולח דיון יומי לקהילה בשעה 20:00 🔥")
        return
    keyboard = [
        [InlineKeyboardButton("🔥 שלח דיון עכשיו", callback_data="send_now")],
        [InlineKeyboardButton("📋 נושאים", callback_data="show_topics")],
    ]
    await update.message.reply_text(
        "🛠 פאנל אדמין - בוט דיונים יומיים\n\nדיון נשלח כל יום בשעה 20:00 אוטומטית",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return

    if query.data == "send_now":
        await query.edit_message_text("⏳ מייצר דיון עם AI...")
        try:
            loop = asyncio.get_event_loop()
            discussion = await loop.run_in_executor(None, generate_discussion_sync)
            await context.bot.send_message(GROUP_ID, discussion)
            await query.edit_message_text(
                "✅ הדיון נשלח לקבוצה!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="back")]])
            )
        except Exception as e:
            await query.edit_message_text("❌ שגיאה: " + str(e))

    elif query.data == "show_topics":
        topics_text = "\n".join(["• " + t for t in TOPICS_POOL[:12]])
        await query.edit_message_text(
            "📋 נושאים:\n\n" + topics_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזור", callback_data="back")]])
        )

    elif query.data == "back":
        keyboard = [
            [InlineKeyboardButton("🔥 שלח דיון עכשיו", callback_data="send_now")],
            [InlineKeyboardButton("📋 נושאים", callback_data="show_topics")],
        ]
        await query.edit_message_text(
            "🛠 פאנל אדמין - בוט דיונים",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.job_queue.run_daily(
        send_daily_discussion,
        time=time(hour=20, minute=0),
        name="daily_discussion"
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    logger.info("בוט דיונים פועל!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
