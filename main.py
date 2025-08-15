import os
import json
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ===== Завантаження фільмів =====
with open("movies.json", "r", encoding="utf-8") as f:
    movies = json.load(f)

# ===== Файли статистики та реакцій =====
STATS_FILE = "stats.json"
REACTIONS_FILE = "reactions.json"

# ===== Завантаження статистики =====
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}

# ===== Завантаження реакцій =====
if os.path.exists(REACTIONS_FILE):
    with open(REACTIONS_FILE, "r", encoding="utf-8") as f:
        reactions = json.load(f)
else:
    reactions = {}

# ===== Параметри з Environment Variables =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
if not TOKEN or not ADMIN_ID:
    raise ValueError("BOT_TOKEN або ADMIN_ID не встановлені")

support_mode_users = set()
reply_mode_admin = {}

# ===== Клавіатури =====
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ])

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

# ===== Збереження =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

def save_reactions():
    with open(REACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(reactions, f, ensure_ascii=False, indent=4)

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.full_name

    user_stats[user_id] = {
        "name": username,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1,
        "last_active": datetime.now().isoformat()
    }
    save_stats()

    await update.message.reply_text(
        "Привіт! Можеш натиснути кнопку для рандомного фільму або ввести код фільму.",
        reply_markup=get_main_keyboard()
    )

# ===== Рандомний фільм =====
async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not movies:
        await query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    film = movies[code]
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=get_film_keyboard(text, code))
    await query.answer()

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_film_keyboard(text, code))
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.", reply_markup=get_main_keyboard())

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

    if user_id == ADMIN_ID and user_id in reply_mode_admin:
        target_user_id = reply_mode_admin[user_id]
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"📩 Відповідь від підтримки:\n\n{text}")
            await update.message.reply_text("✅ Повідомлення відправлено користувачу.")
        except:
            await update.message.reply_text("⚠ Не вдалося відправити повідомлення користувачу.")
        return

    if user_id in support_mode_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Нове повідомлення від користувача:\n👤 {username} (ID: {user_id})\n\n💬 {text}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏ Відповісти", callback_data=f"reply_{user_id}")]])
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

async def stop_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and ADMIN_ID in reply_mode_admin:
        del reply_mode_admin[ADMIN_ID]
        await update.message.reply_text("🚪 Ви вийшли з режиму відповіді.")
    else:
        await update.message.reply_text("⚠ Ви не в режимі відповіді.")

# ===== Реакції =====
async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, movie_code, reaction_type = query.data.split("_")
    user_id = query.from_user.id

    if movie_code not in reactions:
        reactions[movie_code] = {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []}

    # Користувач може обрати тільки одну реакцію одночасно
    for key in reactions[movie_code]:
        if key != reaction_type and user_id in reactions[movie_code][key]:
            reactions[movie_code][key].remove(user_id)

    if user_id not in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].append(user_id)
    
    save_reactions()

    share_text = f"🎬 {movies[movie_code]['title']} - Поділися!"
    await query.message.edit_reply_markup(reply_markup=get_film_keyboard(share_text, movie_code))
    await query.answer(f"Ви проголосували {reaction_type}")

# ===== Розсилка =====
async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str):
    for user_id in user_stats.keys():
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            print(f"Не вдалося відправити користувачу {user_id}: {e}")

async def send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може надсилати повідомлення всім.")
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❌ Введіть текст повідомлення після команди /sendall")
        return
    await broadcast(context, text)
    await update.message.reply_text("✅ Повідомлення надіслано всім користувачам.")

async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Тільки адмін може переглядати статистику.")
        return
    total_users = len(user_stats)
    visits = sum(u.get("visits", 0) for u in user_stats.values())
    stats_text = f"👥 Користувачів: {total_users}\n📈 Відвідувань: {visits}\n\nДеталі:\n"
    for uid, info in user_stats.items():
        stats_text += f"ID: {uid}, Name: {info['name']}, Visits: {info['visits']}, Last Active: {info['last_active']}\n"
    await update.message.reply_text(stats_text)

# ===== Запуск =====
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(TOKEN)
    try:
        bot.delete_webhook()
        print("Webhook видалено, можна запускати polling.")
    except Exception as e:
        print(f"Не вдалося видалити webhook: {e}")

    app = ApplicationBuilder().token(TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stopreply", stop_reply))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CommandHandler("stats", send_stats))

    # Callback
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
   
    # Реакції
    app.add_handler(CallbackQueryHandler(reaction_callback, pattern="^react_"))

    # Відповіді адміна
    app.add_handler(CallbackQueryHandler(reply_callback, pattern="^reply_"))

    # Рандомний фільм
    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="^random_film$"))

    # Повідомлення користувачів
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message))

    # Запуск
    print("Бот запущено!")
    app.run_polling()
