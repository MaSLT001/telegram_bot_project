from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
import re
import logging
import requests
import sys

# Увімкнення детального логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Отримуємо конфіг з Environment Variables ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# --- Перевірка змінних ---
if not TOKEN:
    logging.critical("❌ TELEGRAM_BOT_TOKEN не встановлено в Environment Variables!")
    sys.exit(1)

if not ADMIN_ID or not ADMIN_ID.isdigit():
    logging.critical("❌ ADMIN_ID не встановлено або має невірний формат у Environment Variables!")
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID)

# --- Перевірка валідності токена через Telegram API ---
def check_token(token):
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("ok"):
            logging.info(f"✅ Токен валідний. Бот: {data['result']['first_name']} (@{data['result']['username']})")
            return True
        else:
            logging.critical(f"❌ Помилка від Telegram API: {data}")
            return False
    except requests.RequestException as e:
        logging.critical(f"❌ Помилка під час перевірки токена: {e}")
        return False

if not check_token(TOKEN):
    sys.exit(1)

# --- Завантаження бази фільмів ---
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
    logging.info(f"✅ Завантажено {len(movies)} фільмів із movies.json")
except FileNotFoundError:
    logging.warning("⚠️ Файл movies.json не знайдено, використовую порожню базу")
    movies = {}
except json.JSONDecodeError as e:
    logging.error(f"❌ Помилка у форматі movies.json: {e}")
    movies = {}

# --- Файл для статистики ---
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            user_stats = json.load(f)
        logging.info(f"✅ Завантажено статистику {len(user_stats)} користувачів")
    except json.JSONDecodeError as e:
        logging.error(f"❌ Помилка у форматі stats.json: {e}")
        user_stats = {}
else:
    user_stats = {}
    logging.info("📂 Файл stats.json не знайдено, створю новий при збереженні")

# --- Допоміжні функції ---
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)
    logging.debug("💾 Статистика збережена")

def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!/"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

# --- Хендлери ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.username or update.effective_user.full_name

    if user_id not in user_stats:
        user_stats[user_id] = {"name": user_name, "visits": 1}
    else:
        user_stats[user_id]["visits"] += 1

    save_stats()
    await update.message.reply_text("Привіт! Введи код фільма, і я скажу, що це за фільм.")

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if not movies:
        await update.message.reply_text("⚠️ База фільмів порожня.")
        return

    if code in movies:
        film = movies[code]
        title = escape_markdown(film.get("title", "Без назви"))
        desc = escape_markdown(film.get("desc", ""))
        link = escape_markdown(film.get("link", ""))
        text = f"🎬 *{title}*\n\n{desc}\n\n🔗 {link}"
        await update.message.reply_text(text, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.")

async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str):
    for user_id in user_stats.keys():
        try:
            await context.bot.send_message(chat_id=int(user_id), text=text)
        except Exception as e:
            logging.error(f"Не вдалось відправити користувачу {user_id}: {e}")

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

# --- Запуск бота ---
if __name__ == "__main__":
    logging.info("🚀 Запускаю бота...")
    try:
        app = ApplicationBuilder().token(TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("sendall", send_all))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, find_movie))

        app.run_polling()
    except Exception as e:
        logging.critical(f"❌ Фатальна помилка запуску: {e}")
