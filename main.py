import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)

# ===== Файли для збереження =====
MOVIES_FILE = "movies.json"
STATS_FILE = "user_stats.json"

# ===== Завантаження даних =====
if os.path.exists(MOVIES_FILE):
    with open(MOVIES_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)
else:
    movies = {}  # {код: {"title": "назва", "link": "посилання"}}

if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}  # {user_id: {"name": str, "visits": int, "last_active": str}}

# ===== Параметри =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# ===== Допоміжні функції =====
def save_movies():
    with open(MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=4)

def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

def update_user_stats(user):
    user_id = str(user.id)
    user_name = user.username or user.full_name
    stats = user_stats.get(user_id, {"name": user_name, "visits": 0, "last_active": ""})
    stats["visits"] += 1
    stats["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_stats[user_id] = stats
    save_stats()

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")],
        [InlineKeyboardButton("💬 Підтримка", callback_data="support")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_stats(update.effective_user)
    await update.message.reply_text(
        "Привіт! Введи код фільму, щоб отримати його, або натисни кнопку.",
        reply_markup=get_main_keyboard()
    )

# ===== Callback для кнопок =====
async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    query.answer()
    if movies:
        code, film = random.choice(list(movies.items()))
        await query.message.reply_text(f"🎬 {film['title']}\n🔗 {film['link']}\nКод: {code}")
    else:
        await query.message.reply_text("Список фільмів порожній.")

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    query.answer()
    await query.message.reply_text("💬 Надішліть повідомлення, і я передам його адміну.")

# ===== Обробка повідомлень =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    update_user_stats(user)

    if text in movies:
        film = movies[text]
        await update.message.reply_text(f"🎬 {film['title']}\n🔗 {film['link']}")
    else:
        # Повідомлення до підтримки
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Повідомлення від {user.full_name} (ID: {user.id}):\n{text}"
        )
        await update.message.reply_text("✅ Ваше повідомлення надіслано адміністрації.")

# ===== Статистика для адміна =====
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може переглядати статистику.")
        return

    text = "📊 Статистика користувачів:\n\n"
    for uid, info in user_stats.items():
        text += f"👤 {info['name']} (ID: {uid}) — відвідувань: {info['visits']}, остання активність: {info['last_active']}\n"
    await update.message.reply_text(text)

# ===== Основна функція =====
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", send_stats))

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="random_film"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="support"))

    await app.start()
    print("Бот запущено...")
    await app.idle()

import asyncio
asyncio.run(main())
