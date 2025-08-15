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

# ===== Діапазон рандомних фільмів =====
RANDOM_RANGE = {"min": 1, "max": len(movies)}  # за замовчуванням всі коди

# ===== Клавіатури =====
def get_film_keyboard(share_text, movie_code):
    movie_reacts = reactions.get(movie_code, {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []})
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
        ],
        [
            InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")
        ]
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
        "Привіт! Введи код фільму, щоб отримати інформацію або натисни 🎲 Рандомний фільм."
    )

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ===== Підтримка =====
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    support_mode_users.add(user_id)
    await query.answer()
    await query.message.reply_text("✍ Напишіть своє повідомлення для підтримки, і я передам його.")

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    text = update.message.text

    # Якщо адмін у режимі відповіді
    if user_id == ADMIN_ID and user_id in reply_mode_admin:
        target_user_id = reply_mode_admin[user_id]
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"📩 Відповідь від підтримки:\n\n{text}")
            await update.message.reply_text("✅ Повідомлення відправлено користувачу.")
        except:
            await update.message.reply_text("⚠ Не вдалося відправити повідомлення користувачу.")
        return

    # Якщо користувач пише у підтримку
    if user_id in support_mode_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Нове повідомлення від користувача:\n"
                 f"👤 {username} (ID: {user_id})\n\n"
                 f"💬 {text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏ Відповісти", callback_data=f"reply_{user_id}")]
            ])
        )
        await update.message.reply_text("✅ Ваше повідомлення відправлено в підтримку.")
        support_mode_users.remove(user_id)
    else:
        await find_movie(update, context)

async def reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data.startswith("reply_"):
        target_user_id = int(data.split("_")[1])
        reply_mode_admin[ADMIN_ID] = target_user_id
        await query.answer()
        await query.message.reply_text(
            f"✍ Ви увійшли в режим відповіді користувачу (ID: {target_user_id}).\n"
            f"Введіть повідомлення або напишіть /stopreply щоб вийти."
        )
    elif data == "random_film":
        await send_random_film(update, context)

async def stop_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and ADMIN_ID in reply_mode_admin:
        del reply_mode_admin[ADMIN_ID]
        await update.message.reply_text("🚪 Ви вийшли з режиму відповіді.")
    else:
        await update.message.reply_text("⚠ Ви не в режимі відповіді.")

# ===== Реакції =====
async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data  # формат "react_MOVIECODE_TYPE"
    _, movie_code, reaction_type = data.split("_")
    user_id = query.from_user.id

    if movie_code not in reactions:
        reactions[movie_code] = {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []}

    # Видаляємо попереднє голосування того ж користувача для інших типів
    for key in reactions[movie_code]:
        if user_id in reactions[movie_code][key] and key != reaction_type:
            reactions[movie_code][key].remove(user_id)

    if user_id not in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].append(user_id)

    save_reactions()  # зберігаємо відразу

    # Оновлюємо кнопки
    message = query.message
    share_text = f"🎬 {movies[movie_code]['title']} - Поділися!"
    await message.edit_reply_markup(reply_markup=get_film_keyboard(share_text, movie_code))

    await query.answer(f"Ви проголосували {reaction_type}")

# ===== Рандомний фільм =====
async def send_random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.message.reply_text("❌ Немає доступних фільмів.")
        return

    valid_codes = [code for code in movies.keys() if RANDOM_RANGE["min"] <= int(code) <= RANDOM_RANGE["max"]]
    if not valid_codes:
        await update.callback_query.message.reply_text("❌ Немає фільмів у заданому діапазоні.")
        return

    code = random.choice(valid_codes)
    film = movies[code]
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    await update.callback_query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_film_keyboard(share_text=text, movie_code=code)
    )

# ===== Зміна діапазону =====
async def set_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RANDOM_RANGE
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас немає прав для цієї команди.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Використання: /range min max")
        return

    try:
        min_val = int(context.args[0])
        max_val = int(context.args[1])
        RANDOM_RANGE["min"] = min_val
        RANDOM_RANGE["max"] = max_val
        await update.message.reply_text(f"✅ Діапазон рандомних фільмів встановлено: {min_val} - {max_val}")
    except ValueError:
        await update.message.reply_text("❌ Введіть два числа для діапазону.")

# ===== Розсилка =====
async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str):
    for user_id in user_stats.keys():
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            print(f"Не вдалося відправити користувачу {user_id}: {e}")

async def send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас немає прав для цієї команди.")
        return
    if not context.args:
        await update.message.reply_text("Використання: /sendall текст_повідомлення")
        return

    text = " ".join(context.args)
    await broadcast(context, text)
    await update.message.reply_text("✅ Повідомлення надіслано всім користувачам.")

# ===== Статистика через Telegram =====
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас немає прав для цієї команди.")
        return

    total_users = len(user_stats)
    total_visits = sum(user["visits"] for user in user_stats.values())

    text = f"📊 Статистика користувачів:\n\n"
    text += f"👥 Загальна кількість користувачів: {total_users}\n"
    text += f"📈 Загальна кількість відвідувань: {total_visits}\n\n"
    text += "🔹 Відвідування по користувачах:\n"

    for user_id, info in user_stats.items():
        name = info.get("name", "Unknown")
        visits = info.get("visits", 0)
        text += f"- {name} (ID: {user_id}): {visits} відвідувань\n"

    await update.message.reply_text(text)

# ===== Збереження =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

def save_reactions():
    with open(REACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(reactions, f, ensure_ascii=False, indent=4)

# ===== Запуск бота =====
if __name__ == "__main__":
    app
