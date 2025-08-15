import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# ====== Налаштування Google Drive ======
gauth = GoogleAuth()
gauth.LocalWebserverAuth()  # Або використовуйте .LoadCredentialsFile() для сервіс акаунту
drive = GoogleDrive(gauth)

MOVIES_FILE = "movies.json"
STATS_FILE = "stats.json"

# ====== Завантаження/збереження на локальний файл ======
def load_json(file_name):
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    return {} if "stats" in file_name else {}

def save_json(data, file_name):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Збереження на Google Drive
    file_list = drive.ListFile({'q': f"title='{file_name}'"}).GetList()
    if file_list:
        gfile = file_list[0]
        gfile.SetContentFile(file_name)
        gfile.Upload()
    else:
        gfile = drive.CreateFile({'title': file_name})
        gfile.SetContentFile(file_name)
        gfile.Upload()

# ====== Дані ======
movies = load_json(MOVIES_FILE)
user_stats = load_json(STATS_FILE)

# ====== Основні функції ======
def update_user_stats(user):
    user_id = str(user.id)
    user_name = user.username or user.full_name
    user_stats[user_id] = {
        "name": user_name,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1,
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_json(user_stats, STATS_FILE)

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎥 Випадковий фільм", callback_data="random_film")],
        [InlineKeyboardButton("✉️ Написати в підтримку", callback_data="support")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ====== Команди ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_stats(update.effective_user)
    await update.message.reply_text(
        "Вітаю! Можеш натиснути кнопку для рандомного фільму або ввести код фільму.",
        reply_markup=get_main_keyboard()
    )

async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random
    if not movies:
        await update.callback_query.message.reply_text("Список фільмів порожній.")
        return
    code, film = random.choice(list(movies.items()))
    await update.callback_query.message.reply_text(f"🎬 {film}")

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_stats(update.effective_user)
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        await update.message.reply_text(f"🎬 {film}")
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.")

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "Напишіть своє повідомлення, і воно буде передане адміну."
    )

async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може переглядати статистику.")
        return

    text = "📊 Статистика користувачів:\n\n"
    for uid, info in user_stats.items():
        text += f"👤 {info['name']} (ID: {uid}) — відвідувань: {info['visits']} | остання активність: {info['last_active']}\n"
    await update.message.reply_text(text)

async def add_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може додавати фільми.")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Використання: /addmovie <код> <назва> <посилання>")
        return

    code = args[0]
    name = args[1]
    link = args[2]
    movies[code] = f"{name} — {link}"
    save_json(movies, MOVIES_FILE)
    await update.message.reply_text(f"✅ Фільм додано: {name} ({code})")

# ====== Основна функція ======
async def main():
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CommandHandler("addmovie", add_movie))
    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="random_film"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="support"))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), find_movie))

    print("Бот запущено...")
    await app.start()
    await app.idle()

import asyncio
asyncio.run(main())
