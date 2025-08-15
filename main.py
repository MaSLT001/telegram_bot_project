import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ===== Файли =====
MOVIES_FILE = "movies.json"
STATS_FILE = "user_stats.json"
SERVICE_ACCOUNT_FILE = "/etc/secrets/service_account.json"
SHEET_NAME = "BotStats"

# ===== Змінні =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# ===== Завантаження фільмів =====
if os.path.exists(MOVIES_FILE):
    with open(MOVIES_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)
else:
    movies = {}

# ===== Локальна статистика =====
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}

# ===== Збереження локальної статистики =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

# ===== Google Sheets =====
scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
gc = gspread.authorize(creds)

try:
    sh = gc.open(SHEET_NAME)
except gspread.SpreadsheetNotFound:
    sh = gc.create(SHEET_NAME)
    sh.share(None, perm_type='anyone', role='writer')
worksheet = sh.sheet1

# ===== Оновлення Google статистики =====
def update_google_stats(user_id, user_name):
    records = worksheet.get_all_records()
    for i, record in enumerate(records, start=2):
        if str(record.get("UserID")) == str(user_id):
            visits = int(record.get("Visits", 0)) + 1
            worksheet.update(f"C{i}", visits)
            worksheet.update(f"D{i}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return
    # Якщо користувача немає — додаємо
    worksheet.append_row([user_name, user_id, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

# ===== Оновлення користувача =====
def update_user(user):
    user_id = str(user.id)
    user_name = user.username or user.full_name
    user_stats[user_id] = {
        "name": user_name,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1,
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_stats()
    update_google_stats(user_id, user_name)

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user(update.effective_user)
    await update.message.reply_text(
        "Привіт! Введи код фільму, щоб отримати його назву та посилання."
    )

# ===== Пошук фільму =====
async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user(update.effective_user)
    code = update.message.text.strip()
    film = movies.get(code)
    if film:
        text = f"🎬 {film.get('title')}\n🔗 {film.get('link')}"
    else:
        text = "❌ Фільм з таким кодом не знайдено."
    await update.message.reply_text(text)

# ===== Статистика для адміна =====
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може переглядати статистику.")
        return

    text = "📊 Статистика користувачів:\n\n"
    for uid, info in user_stats.items():
        text += f"👤 {info['name']} (ID: {uid}) — відвідувань: {info['visits']}\n"
    await update.message.reply_text(text)

# ===== Основна функція =====
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), find_movie))

    await app.start()
    print("Бот запущено...")
    await app.idle()

import asyncio
asyncio.run(main())
