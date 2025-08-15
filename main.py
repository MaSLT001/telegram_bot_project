import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

STATS_FILE = "stats.json"
MOVIES_FILE = "movies.json"

# ======= ФУНКЦІЇ СТАТИСТИКИ =======
def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

stats = load_stats()

# ======= КОМАНДИ =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in stats:
        stats[user_id] = {"name": update.effective_user.full_name, "visits": 0}
    stats[user_id]["visits"] += 1
    save_stats(stats)

    keyboard = [
        [InlineKeyboardButton("🎥 Випадковий фільм", callback_data="random_film")],
        [InlineKeyboardButton("✉️ Написати в підтримку", callback_data="support")]
    ]
    await update.message.reply_text(
        f"Вітаю, {update.effective_user.full_name}!\n"
        f"Ви відвідали бота {stats[user_id]['visits']} раз(ів).",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = "📊 Статистика відвідувань:\n"
    for uid, data in stats.items():
        text += f"{data['name']}: {data['visits']} раз(ів)\n"
    await update.message.reply_text(text)

# ======= ФІЛЬМИ =======
def load_movies():
    if os.path.exists(MOVIES_FILE):
        with open(MOVIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = load_movies()
    if not movies:
        await update.callback_query.answer("Список фільмів порожній.")
        return
    import random
    film = random.choice(movies)
    await update.callback_query.message.reply_text(f"🎬 {film}")

# ======= ПІДТРИМКА =======
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "Напишіть своє повідомлення, і воно буде передане адміну."
    )

# ======= ЗАПУСК =======
import asyncio

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="random_film"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="support"))

    print("Бот запущено...")
    asyncio.run(app.run_polling())
