import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ===== Завантаження фільмів =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

# ===== Статистика користувачів =====
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}

# ===== Параметри з Environment Variables =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

if not TOKEN or not ADMIN_ID:
    raise ValueError("BOT_TOKEN або ADMIN_ID не встановлені в environment variables.")

# ===== Клавіатури =====
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ])

# ===== Збереження =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.username or update.effective_user.full_name

    # Оновлюємо статистику користувача
    user_stats[user_id] = {
        "name": user_name,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1
    }
    save_stats()

    await update.message.reply_text(
        "Привіт! Можеш натиснути кнопку для рандомного фільму або ввести код фільму.",
        reply_markup=get_main_keyboard()
    )

# ===== Рандомний фільм =====
async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not movies:
        await query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    film = movies[code]
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    await query.message.reply_text(text, parse_mode="Markdown")
    await query.answer()

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.", reply_markup=get_main_keyboard())

# ===== Розсилка =====
async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str):
    for user_id in user_stats.keys():
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            print(f"Не вдалося відправити користувачу {user_id}: {e}")

async def send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може надсилати повідомлення всім.")
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❌ Введіть текст повідомлення після команди /sendall")
        return
    await broadcast(context, text)
    await update.message.reply_text("✅ Повідомлення надіслано всім користувачам.")

# ===== Статистика =====
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може переглядати статистику.")
        return

    total_users = len(user_stats)
    total_visits = sum(u.get("visits", 0) for u in user_stats.values())
    
    user_list = "\n".join(
        f"👤 {u.get('name', 'Unknown')} (ID: {uid}) - Відвідувань: {u.get('visits', 0)}"
        for uid, u in user_stats.items()
    )

    text = f"👥 Користувачів: {total_users}\n📈 Відвідувань: {total_visits}\n\nСписок користувачів:\n{user_list}"
    await update.message.reply_text(text)

# ===== Запуск =====
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(TOKEN)
    try:
        bot.delete_webhook()
        print("Webhook видалено, можна запускати polling.")
    except Exception as e:
        print(f"Не вдалося видалити webhook: {e}")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, find_movie))
    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="^random_film$"))

    print("Бот запущено!")
    app.run_polling()
