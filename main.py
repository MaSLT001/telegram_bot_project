import os
import json
import random
import requests
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ===== ENV перемінні =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Для оновлення stats.json на GitHub
GITHUB_REPO = os.getenv("GITHUB_REPO")    # Формат: username/repo
GITHUB_FILE_PATH = "stats.json"

if not TOKEN:
    raise ValueError("BOT_TOKEN не встановлено")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID не встановлено")
if not GITHUB_TOKEN or not GITHUB_REPO:
    raise ValueError("GITHUB_TOKEN або GITHUB_REPO не встановлено")

ADMIN_ID = int(ADMIN_ID)

# ===== Фільми =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except:
    movies = {}

# ===== Статистика =====
STATS_FILE = "stats.json"
user_stats = {}
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)

def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, indent=2, ensure_ascii=False)
    github_update_stats()  # Одразу оновлюємо GitHub

def github_update_stats():
    """Оновлює stats.json на GitHub"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = None

    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        sha = r.json()["sha"]

    content = base64.b64encode(json.dumps(user_stats, indent=2, ensure_ascii=False).encode()).decode()
    data = {"message": "Update stats.json", "content": content}
    if sha:
        data["sha"] = sha

    response = requests.put(url, headers=headers, json=data)
    if response.status_code in [200, 201]:
        print("✅ stats.json успішно оновлено на GitHub")
    else:
        print("❌ Помилка оновлення stats.json:", response.text)

def add_user(uid, username, first_name):
    uid = str(uid)
    if uid not in user_stats:
        user_stats[uid] = {"username": username, "first_name": first_name}
        save_stats()

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

# ===== Показ фільму =====
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, film):
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text))

async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update.callback_query, context, movies[code])
    await update.callback_query.answer()

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"Привіт, {user.first_name}!👋 Введи код фільму або назву, або натисни кнопку нижче щоб отримати фільм😉",
        reply_markup=main_keyboard()
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total = len(user_stats)
    users_list = "\n".join(
        [f"{uid} — @{data.get('username', 'нема')} ({data.get('first_name','')})"
         for uid, data in user_stats.items()]
    )
    text = f"📊 Всього користувачів: {total}\n\n{users_list}"
    await update.message.reply_text(text if len(text) < 4000 else f"📊 Всього користувачів: {total}")

# ===== Пошук фільму =====
async def movie_by_code_or_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().lower()
    add_user(update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    # Спочатку шукаємо за кодом
    if query in movies:
        await show_film(update, context, movies[query])
        return

    # Потім шукаємо за назвою
    found = None
    for film in movies.values():
        if query in film["title"].lower():
            found = film
            break

    if found:
        await show_film(update, context, found)
    else:
        await update.message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard())

# ===== Main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))

    # Callback
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))

    # Повідомлення
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code_or_title))

    print("✅ Бот запущений")
    app.run_polling()

if __name__ == "__main__":
    main()
