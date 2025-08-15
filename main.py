import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
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

# ===== Параметри з Environment Variables =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set.")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID is not set.")

ADMIN_ID = int(ADMIN_ID)

support_mode_users = set()
reply_mode_admin = {}  # {admin_id: user_id_to_reply}

# ===== Клавіатури =====
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ])

def get_film_keyboard(share_text):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=share_text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
        ],
        [
            InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")
        ]
    ])

# ===== Показ фільму =====
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    if code not in movies:
        msg = "❌ Фільм з таким кодом не знайдено."
        if update.message:
            await update.message.reply_text(msg, reply_markup=get_main_keyboard())
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg, reply_markup=get_main_keyboard())
        return

    film = movies[code]
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"

    keyboard = get_film_keyboard(text)

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await update.callback_query.answer()

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
        "Привіт! Введи код фільму або обери рандомний фільм.",
        reply_markup=get_main_keyboard()
    )

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    await show_film(update, context, code)

# ===== Рандомний фільм =====
async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not movies:
        await query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update, context, code)

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
    if not data.startswith("reply_"):
        return
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

# ===== Збереження =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

# ===== Запуск бота =====
if __name__ == "__main__":
    bot = Bot(token=TOKEN)
    try:
        bot.delete_webhook()
        print("Webhook видалено, можна запускати polling.")
    except Exception as e:
        print(f"Не вдалося видалити webhook: {e}")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stopreply", stop_reply))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(reply_callback, pattern="^reply_"))
    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="^random_film$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message))

    print("Бот запущений...")
    app.run_polling()
