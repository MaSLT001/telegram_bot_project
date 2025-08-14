import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ===== Налаштування з Environment Variables =====
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ TOKEN не знайдено! Додай його у змінні середовища на Render.")

ADMIN_ID = int(os.getenv("ADMIN_ID", "381038534"))

# ===== Завантаження бази фільмів =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

# ===== Завантаження статистики =====
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}

# Словник для збереження стану звернень
feedback_waiting = {}

# ===== Функції =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.username or update.effective_user.full_name

    user_stats[user_id] = {
        "name": user_name,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1
    }
    save_stats()

    await update.message.reply_text("Привіт! Введи код фільма, і я скажу, що це за фільм.")

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"

        keyboard = [
            [
                InlineKeyboardButton("💾 Зберегти у Вибране", switch_inline_query=text),
                InlineKeyboardButton("✉️ Залишити звернення", callback_data=f"feedback_{code}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("feedback_"):
        code = data.split("_", 1)[1]
        film = movies.get(code)
        if film:
            user_id = str(query.from_user.id)
            feedback_waiting[user_id] = code
            await query.message.reply_text(
                f"✉️ Надішліть своє звернення щодо фільму *{film['title']}*",
                parse_mode="Markdown"
            )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()

    if user_id in feedback_waiting:
        code = feedback_waiting.pop(user_id)
        film = movies.get(code)
        if film:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📩 Звернення від @{update.effective_user.username or update.effective_user.full_name} "
                     f"щодо фільму *{film['title']}*:\n\n{text}",
                parse_mode="Markdown"
            )
            await update.message.reply_text("✅ Ваше звернення надіслано!")
        return

    await find_movie(update, context)

async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str):
    for user_id in user_stats.keys():
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            print(f"Не вдалось відправити користувачу {user_id}: {e}")

async def send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас немає прав для цієї команди.")
        return

    if not context.args:
        await update.message.reply_text("Используй: /sendall текст_сообщения")
        return

    text = " ".join(context.args)
    await broadcast(context, text)
    await update.message.reply_text("✅ Повідомлення відправлено всім користувачам.")

# ===== Запуск бота =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущено...")
    app.run_polling()
