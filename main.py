import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ===== Завантаження фільмів =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

# ===== Статистика =====
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}

# ===== Реакції =====
REACTIONS_FILE = "reactions.json"
if os.path.exists(REACTIONS_FILE):
    with open(REACTIONS_FILE, "r", encoding="utf-8") as f:
        reactions = json.load(f)
else:
    reactions = {}  # {movie_code: {reaction_type: [user_id, ...]}}

# ===== Параметри з Environment Variables =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables.")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID is not set in environment variables.")

ADMIN_ID = int(ADMIN_ID)

support_mode_users = set()
reply_mode_admin = {}  # {admin_id: user_id_to_reply}

# ===== Клавіатури =====
def get_film_keyboard(share_text, movie_code):
    movie_reacts = reactions.get(movie_code, {})
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=share_text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
        ],
        [
            InlineKeyboardButton(f"👍 {len(movie_reacts.get('like', []))}", callback_data=f"react_{movie_code}_like"),
            InlineKeyboardButton(f"👎 {len(movie_reacts.get('dislike', []))}", callback_data=f"react_{movie_code}_dislike"),
            InlineKeyboardButton(f"😂 {len(movie_reacts.get('laugh', []))}", callback_data=f"react_{movie_code}_laugh"),
            InlineKeyboardButton(f"❤️ {len(movie_reacts.get('heart', []))}", callback_data=f"react_{movie_code}_heart"),
            InlineKeyboardButton(f"💩 {len(movie_reacts.get('poop', []))}", callback_data=f"react_{movie_code}_poop")
        ]
    ])

def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_movie")]
    ])

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.username or update.effective_user.full_name

    user_stats[user_id] = {
        "name": user_name,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1
    }
    save_stats()

    await update.message.reply_text(
        "Привіт! Введи код фільму або обери рандомний фільм:",
        reply_markup=get_start_keyboard()
    )

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE, code=None):
    if not code:
        code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_film_keyboard(share_text=text, movie_code=code)
        )
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.")

async def random_movie_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    query.answer()
    if not movies:
        await query.message.reply_text("Фільми відсутні.")
        return
    code = random.choice(list(movies.keys()))
    await find_movie(update=query, context=context, code=code)

# ===== Реакції =====
async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    _, movie_code, reaction_type = data.split("_")
    user_id = query.from_user.id

    if movie_code not in reactions:
        reactions[movie_code] = {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []}

    # Видаляємо попереднє голосування іншого типу
    for key in reactions[movie_code]:
        if user_id in reactions[movie_code][key] and key != reaction_type:
            reactions[movie_code][key].remove(user_id)

    if user_id not in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].append(user_id)
        save_reactions()

    share_text = f"🎬 {movies[movie_code]['title']} - Поділися!"
    await query.message.edit_reply_markup(reply_markup=get_film_keyboard(share_text, movie_code))
    await query.answer(f"Ви проголосували {reaction_type}")

# ===== Збереження =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

def save_reactions():
    with open(REACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(reactions, f, ensure_ascii=False, indent=4)

# ===== Запуск бота =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(random_movie_callback, pattern="^random_movie$"))
    app.add_handler(CallbackQueryHandler(reaction_callback, pattern="^react_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, find_movie))

    print("Бот запущений...")
    app.run_polling()
