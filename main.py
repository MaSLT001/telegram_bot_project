from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
import re
import logging

# Увімкнення детального логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)

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
    logging.info("📂 Файл stats.json не знайдено, створюю новий при збереженні")

# --- Конфіг ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7572398720:AAEJgReqQ3ARPFZFhwlYMaH9E_DK4Y1Lx6E")
ADMIN_ID = int(os.getenv("ADMIN_ID", "381038534"))

# --- Допоміжні функції ---
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)
    logging.debug("💾 Статистика збережена")

def escape_markdown(text: str) -> str:
    """Екранує спецсимволи для MarkdownV2"""
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
