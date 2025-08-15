import json
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import io

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DRIVE_FILE_NAME = "bot_data.json"
SERVICE_ACCOUNT_FILE = "service_account.json"

# ======= ПІДКЛЮЧЕННЯ ДО GOOGLE DRIVE =======
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)

# ======= ФУНКЦІЇ DRIVE =======
def find_drive_file(file_name):
    results = service.files().list(q=f"name='{file_name}' and trashed=false",
                                   spaces='drive',
                                   fields="files(id, name)").execute()
    items = results.get('files', [])
    return items[0] if items else None

def download_data():
    file = find_drive_file(DRIVE_FILE_NAME)
    if not file:
        return {"stats": {}, "movies": []}
    request = service.files().get_media(fileId=file["id"])
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return json.load(fh)

def upload_data(data):
    file = find_drive_file(DRIVE_FILE_NAME)
    fh = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    media = MediaIoBaseUpload(fh, mimetype="application/json")
    if file:
        service.files().update(fileId=file["id"], media_body=media).execute()
    else:
        service.files().create(body={"name": DRIVE_FILE_NAME}, media_body=media, fields="id").execute()

# ======= ЗАВАНТАЖЕННЯ ДАНИХ =======
data = download_data()
stats = data.get("stats", {})
movies = data.get("movies", [])

# ======= КОМАНДИ =======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in stats:
        stats[user_id] = {"name": update.effective_user.full_name, "visits": 0}
    stats[user_id]["visits"] += 1
    upload_data({"stats": stats, "movies": movies})

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
    for uid, data_user in stats.items():
        text += f"{data_user['name']}: {data_user['visits']} раз(ів)\n"
    await update.message.reply_text(text)

async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.answer("Список фільмів порожній.")
        return
    film = random.choice(movies)
    await update.callback_query.message.reply_text(f"🎬 {film}")

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "Напишіть своє повідомлення, і воно буде передане адміну."
    )

# ======= ЗАПУСК БОТА =======
import asyncio

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="random_film"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="support"))

    print("Бот запущено...")
    asyncio.run(app.run_polling())
