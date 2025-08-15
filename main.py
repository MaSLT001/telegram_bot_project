import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ===== Завантаження фільмів =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

# ===== Статистика користувачів =====
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            user_stats = json.load(f)
    except json.JSONDecodeError:
        user_stats = {}
else:
    user_stats = {}

# ===== Реакції =====
REACTIONS_FILE = "reactions.json"
if os.path.exists(REACTIONS_FILE):
    try:
        with open(REACTIONS_FILE, "r", encoding="utf-8") as f:
            reactions = json.load(f)
    except json.JSONDecodeError:
        reactions = {}
else:
    reactions = {}  # {movie_code: {reaction_type: [user_id, ...]}}

# ===== Параметри з Environment Variables =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
if not TOKEN or not ADMIN_ID:
    raise ValueError("BOT_TOKEN або ADMIN_ID не встановлені в environment variables.")

# ===== Стан підтримки =====
support_mode_users = set()
reply_mode_admin = {}  # {admin_id: user_id_to_reply}

# ===== Клавіатури =====
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ])

def get_film_keyboard(share_text, movie_code):
    movie_reacts = reactions.get(movie_code, {})
    # гарантуємо наявність ключів
    for key in ["like", "dislike", "laugh", "heart", "poop"]:
        movie_reacts.setdefault(key, [])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=share_text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
        ],
        [
            InlineKeyboardButton(f"👍 {len(movie_reacts['like'])}", callback_data=f"react_{movie_code}_like"),
            InlineKeyboardButton(f"👎 {len(movie_reacts['dislike'])}", callback_data=f"react_{movie_code}_dislike"),
            InlineKeyboardButton(f"😂 {len(movie_reacts['laugh'])}", callback_data=f"react_{movie_code}_laugh"),
            InlineKeyboardButton(f"❤️ {len(movie_reacts['heart'])}", callback_data=f"react_{movie_code}_heart"),
            InlineKeyboardButton(f"💩 {len(movie_reacts['poop'])}", callback_data=f"react_{movie_code}_poop"),
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
    user_name = update.effective_user.username or update.effective_user.full_name

    user_stats[user_id] = {
        "name": user_name,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1
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
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_film_keyboard(text, code)
    )
    await query.answer()

# ===== Пошук фільму по коду (звичайне текстове повідомлення) =====
async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=get_film_keyboard(text, code)
        )
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

    # Якщо адмін у режимі відповіді — відсилаємо його текст адресату
    if user_id == ADMIN_ID and user_id in reply_mode_admin:
        target_user_id = reply_mode_admin[user_id]
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"📩 Відповідь від підтримки:\n\n{text}")
            await update.message.reply_text("✅ Повідомлення відправлено користувачу.")
        except Exception:
            await update.message.reply_text("⚠ Не вдалося відправити повідомлення користувачу.")
        return

    # Якщо користувач написав у підтримку
    if user_id in support_mode_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Нове повідомлення від користувача:\n👤 {username} (ID: {user_id})\n\n💬 {text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏ Відповісти", callback_data=f"reply_{user_id}")]
            ])
        )
        await update.message.reply_text("✅ Ваше повідомлення відправлено в підтримку.")
        support_mode_users.remove(user_id)
    else:
        # Якщо це не підтримка — спробуємо знайти фільм по коду
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

    # Ініціалізація контейнера для фільму
    if movie_code not in reactions:
        reactions[movie_code] = {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []}

    # Прибираємо інші реакції цього користувача для цього фільму
    for key in reactions[movie_code]:
        if key != reaction_type and user_id in reactions[movie_code][key]:
            reactions[movie_code][key].remove(user_id)

    # Тогл обраної реакції (повторне натискання — знімає реакцію)
    if user_id not in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].append(user_id)
    else:
        reactions[movie_code][reaction_type].remove(user_id)

    # Зберігаємо ЗАВЖДИ після будь-якої зміни
    save_reactions()

    # Оновлюємо клавіатуру з актуальними лічильниками
    movie_reacts = reactions[movie_code]
    share_text = f"🎬 {movies[movie_code]['title']}\n\n{movies[movie_code]['desc']}\n\n🔗 {movies[movie_code]['link']}"
    await query.message.edit_reply_markup(
        reply_markup=get_film_keyboard(share_text, movie_code)
    )

    await query.answer("✅ Реакція збережена!")


# ===== Статистика користувачів =====
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас немає доступу до цієї команди.")
        return

    total_users = len(user_stats)
    total_visits = sum(u.get("visits", 0) for u in user_stats.values())

    user_list = "\n".join(
        f"👤 {u.get('name', 'Unknown')} (ID: {uid}) — {u.get('visits', 0)} відвідувань"
        for uid, u in user_stats.items()
    )

    text = f"📊 Статистика користувачів:\n" \
           f"👥 Всього користувачів: {total_users}\n" \
           f"📈 Всього відвідувань: {total_visits}\n\n" \
           f"{user_list}"

    await update.message.reply_text(text)


# ===== Розсилка користувачам =====
async def sendall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас немає доступу.")
        return

    if not context.args:
        await update.message.reply_text("Використання: /sendall <текст повідомлення>")
        return

    message_text = " ".join(context.args)
    sent_count, failed_count = 0, 0

    for uid in user_stats.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=message_text)
            sent_count += 1
        except Exception:
            failed_count += 1

    await update.message.reply_text(
        f"✅ Розсилка завершена!\n"
        f"📤 Надіслано: {sent_count}\n"
        f"⚠ Не вдалося: {failed_count}"
    )


# ===== Головна =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("sendall", sendall_command))
    app.add_handler(CommandHandler("stopreply", stop_reply))

    # Callback-и
    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="random_film"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="support"))
    app.add_handler(CallbackQueryHandler(reply_callback, pattern="reply_"))
    app.add_handler(CallbackQueryHandler(reaction_callback, pattern="react_"))

    # Повідомлення
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message))

    print("🤖 Бот запущений...")
    app.run_polling()

