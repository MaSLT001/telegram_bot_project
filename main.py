import json
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from dotenv import load_dotenv

TOKEN = "ТОКЕН_ТВОГО_БОТА"
ADMIN_ID = 123456789  # заміни на свій Telegram ID
# ===== Завантажуємо токен і ID з .env =====
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ===== Завантаження даних =====
# ===== Завантаження фільмів =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

# ===== Завантаження реакцій =====
try:
    with open("reactions.json", "r", encoding="utf-8") as f:
        reactions = json.load(f)
except FileNotFoundError:
    reactions = {}

# ===== Завантаження користувачів =====
try:
    with open("users.json", "r", encoding="utf-8") as f:
        user_stats = json.load(f)
except FileNotFoundError:
    user_stats = {}

# ===== Збереження даних =====
# ===== Функції збереження =====
def save_reactions():
    with open("reactions.json", "w", encoding="utf-8") as f:
        json.dump(reactions, f, ensure_ascii=False, indent=2)
@@ -31,13 +43,7 @@
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=2)

# ===== Список фільмів =====
movies = {
    "film1": {"title": "Фільм 1", "desc": "Опис фільму 1", "link": "https://example.com/1"},
    "film2": {"title": "Фільм 2", "desc": "Опис фільму 2", "link": "https://example.com/2"},
}

# ===== Клавіатура фільму =====
# ===== Генерація клавіатури фільму =====
def get_film_keyboard(share_text, movie_code):
    movie_reacts = reactions.get(movie_code, {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []})
    keyboard = [
@@ -66,7 +72,14 @@
        user_stats[str(user_id)]["visits"] += 1
    save_users()

    await update.message.reply_text("🎬 Привіт! Обери фільм:", reply_markup=get_film_keyboard("Поділися цим фільмом!", "film1"))
    if movies:
        first_movie_code = next(iter(movies))
        await update.message.reply_text(
            "🎬 Привіт! Ось перший фільм:",
            reply_markup=get_film_keyboard("Поділися цим фільмом!", first_movie_code)
        )
    else:
        await update.message.reply_text("❌ Немає доступних фільмів.")

async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
@@ -100,39 +113,38 @@
    if movie_code not in reactions:
        reactions[movie_code] = {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []}

    # Прибираємо з інших реакцій
    for key in reactions[movie_code]:
        if user_id in reactions[movie_code][key] and key != reaction_type:
            reactions[movie_code][key].remove(user_id)

    # Перемикаємо поточну реакцію
    if user_id in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].remove(user_id)
    else:
        reactions[movie_code][reaction_type].append(user_id)

    save_reactions()

    share_text = f"🎬 {movies[movie_code]['title']}\n\n{movies[movie_code]['desc']}\n\n{movies[movie_code]['link']}"
    movie_data = movies.get(movie_code, {"title": "Невідомо", "desc": "", "link": ""})
    share_text = f"🎬 {movie_data['title']}\n\n{movie_data['desc']}\n\n{movie_data['link']}"
    await query.message.edit_reply_markup(reply_markup=get_film_keyboard(share_text, movie_code))
    await query.answer("✅ Реакція збережена!")

# ===== Головний запуск =====
# ===== Запуск бота =====
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = Bot(TOKEN)
    try:
        bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook видалено, старі оновлення очищені.")
    except Exception as e:
        print(f"⚠ Не вдалося видалити webhook: {e}")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CallbackQueryHandler(reaction_callback, pattern="^react_"))

    print("🚀 Бот запущений...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
