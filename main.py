from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import json
import os
import re
import logging
import requests
import sys

# Логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Config ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    logging.critical("❌ TELEGRAM_BOT_TOKEN не встановлено!")
    sys.exit(1)

if not ADMIN_ID or not ADMIN_ID.isdigit():
    logging.critical("❌ ADMIN_ID не встановлено або невірний формат!")
    sys.exit(1)

ADMIN_ID = int(ADMIN_ID)

# --- Перевірка токена ---
def check_token(token):
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("ok"):
            logging.info(f"✅ Токен валідний. Бот: {data['result']['first_name']} (@{data['result']['username']})")
            return True
        else:
            logging.critical(f"❌ Помилка API Telegram: {data}")
            return False
    except requests.RequestException as e:
        logging.critical(f"❌ Помилка під час перевірки токена: {e}")
        return False

if not check_token(TOKEN):
    sys.exit(1)

# --- Завантаження фільмів ---
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
    logging.info(f"✅ Завантажено {len(movies)} фільмів")
except FileNotFoundError:
    logging.warning("⚠️ movies.json не знайдено, використовую порожню базу")
    movies = {}
except json.JSONDecodeError as e:
    logging.error(f"❌ Помилка у форматі movies.json: {e}")
    movies = {}

# --- Статистика користувачів ---
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            user_stats = json.load(f)
        logging.info(f"✅ Завантажено статистику {len(user_stats)} користувачів")
    except json.JSONDecodeError:
        user_stats = {}
else:
    user_stats = {}

# --- Реакції ---
REACTIONS_FILE = "reactions.json"
if os.path.exists(REACTIONS_FILE):
    try:
        with open(REACTIONS_FILE, "r", encoding="utf-8") as f:
            reactions_data = json.load(f)
    except json.JSONDecodeError:
        reactions_data = {}
else:
    reactions_data = {}

# --- Функції збереження ---
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

def save_reactions():
    with open(REACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(reactions_data, f, ensure_ascii=False, indent=4)

# --- Екранування Markdown ---
def escape_markdown(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!/"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

# --- Кнопки ---
def get_reaction_keyboard(movie_code):
    counts = reactions_data.get(movie_code, {👍: 0, 👎: 0, 😂: 0, ❤️: 0, 💩: 0})
    buttons = [
        [
            InlineKeyboardButton(f"👍 {counts['👍']}", callback_data=f"react|{movie_code}|👍"),
            InlineKeyboardButton(f"👎 {counts['👎']}", callback_data=f"react|{movie_code}|👎"),
            InlineKeyboardButton(f"😂 {counts['😂']}", callback_data=f"react|{movie_code}|😂"),
            InlineKeyboardButton(f"❤️ {counts['❤️']}", callback_data=f"react|{movie_code}|❤️"),
            InlineKeyboardButton(f"💩 {counts['💩']}", callback_data=f"react|{movie_code}|💩")
        ],
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=movie_code),
            InlineKeyboardButton("💖 Підтримка", url="https://send.monobank.ua/jar/ВАШ_ЛІНК")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

# --- Команди ---
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

        # Ініціалізація реакцій
        if code not in reactions_data:
            reactions_data[code] = {"👍": 0, "👎": 0, "😂": 0, "❤️": 0, "💩": 0}
            save_reactions()

        text = f"🎬 *{title}*\n\n{desc}\n\n🔗 {link}"
        await update.message.reply_text(
            text,
            parse_mode="MarkdownV2",
            reply_markup=get_reaction_keyboard(code)
        )
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.")

# --- Обробка реакцій ---
async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, movie_code, emoji = query.data.split("|")

    if movie_code not in reactions_data:
        reactions_data[movie_code] = {"👍": 0, "👎": 0, "😂": 0, "❤️": 0, "💩": 0}

    reactions_data[movie_code][emoji] += 1
    save_reactions()

    # Оновлюємо кнопки з новими лічильниками
    await query.edit_message_reply_markup(reply_markup=get_reaction_keyboard(movie_code))

# --- Розсилка ---
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
        await update.message.reply_text("Використай: /sendall текст_повідомлення")
        return

    text = " ".join(context.args)
    await broadcast(context, text)
    await update.message.reply_text("✅ Повідомлення відправлено всім користувачам.")

# --- Запуск ---
if __name__ == "__main__":
    logging.info("🚀 Запускаю бота...")
    try:
        app = ApplicationBuilder().token(TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("sendall", send_all))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, find_movie))
        app.add_handler(CallbackQueryHandler(handle_reaction, pattern=r"^react\|"))

        app.run_polling()
    except Exception as e:
        logging.critical(f"❌ Фатальна помилка: {e}")
