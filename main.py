import os
import json
import random
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from googletrans import Translator
from thefuzz import process

# ===== ENV перемінні =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")

if not TOKEN or not ADMIN_ID or not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
    raise ValueError("Перевірте, що всі змінні оточення встановлені")

translator = Translator()

# ===== Фільми =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except:
    movies = {}

# ===== Кеш перекладів =====
TRANSLATE_CACHE_FILE = "translate_cache.json"
translate_cache = {}
if os.path.exists(TRANSLATE_CACHE_FILE):
    with open(TRANSLATE_CACHE_FILE, "r", encoding="utf-8") as f:
        translate_cache = json.load(f)

def translate_text(text: str) -> str:
    """Переклад з кешем"""
    if text.lower() in translate_cache:
        return translate_cache[text.lower()]
    try:
        translated = translator.translate(text, src='ru', dest='uk').text
    except:
        translated = text
    translate_cache[text.lower()] = translated
    # Одразу зберігаємо кеш
    with open(TRANSLATE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(translate_cache, f, indent=2, ensure_ascii=False)
    return translated

# ===== Статистика =====
STATS_FILE = "stats.json"
user_stats = {}
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)

# ===== GitHub save =====
def save_stats():
    # Локальне збереження
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, indent=2, ensure_ascii=False)
    
    # GitHub збереження
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_user(GITHUB_OWNER).get_repo(GITHUB_REPO)
        content = json.dumps(user_stats, indent=2, ensure_ascii=False)
        try:
            file = repo.get_contents(STATS_FILE)
            repo.update_file(path=STATS_FILE, message="Update stats.json", content=content, sha=file.sha)
        except:
            repo.create_file(path=STATS_FILE, message="Create stats.json", content=content)
    except Exception as e:
        print("❌ Помилка при збереженні на GitHub:", e)

# ===== Клавіатури =====
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ])

def film_keyboard(text):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
        ],
        [
            InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")
        ]
    ])

# ===== Пошук фільму =====
def find_film_by_name(name: str):
    """Нечіткий пошук фільму по назві"""
    titles = [f['title'] for f in movies.values()]
    match, score = process.extractOne(name, titles)
    if score >= 60:  # мінімальний поріг схожості
        return next(f for f in movies.values() if f['title'] == match)
    return None

# ===== Показ фільму =====
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    translated = translate_text(code)

    # Пошук по коду
    film = movies.get(code)
    if not film:
        # Нечіткий пошук по назві
        film = find_film_by_name(translated)
    if not film:
        await update.message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard())
        return
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text))

async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update.callback_query, context, code)
    await update.callback_query.answer()

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": user.username, "first_name": user.first_name}
        save_stats()
    await update.message.reply_text(
        f"Привіт, {user.first_name}!👋 Введи код фільму або натисни кнопку нижче щоб ми тобі запропонували фільм😉",
        reply_markup=main_keyboard()
    )

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    save_stats()
    await show_film(update, context, code)

# ===== Main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code))
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    print("✅ Бот запущений")
    app.run_polling()

if __name__ == "__main__":
    main()
