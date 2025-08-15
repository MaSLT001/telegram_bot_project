from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import json
import os

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

TOKEN = "TOKEN"
ADMIN_ID = ADMIN_ID  # заміни на свій Telegram ID

# Збереження стану користувачів, які пишуть у підтримку
support_mode_users = set()

# ===== Клавіатури =====
def get_support_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💬 Підтримка", callback_data="support")]])

def get_film_keyboard(share_text):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=share_text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
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
        "Привіт! Введи код фільму, щоб отримати інформацію.",
        reply_markup=get_support_keyboard()
    )

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=get_film_keyboard(share_text=text)
        )
    else:
        await update.message.reply_text("❌ Фільм з таким кодом не знайдено.")

# ===== Підтримка =====
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    support_mode_users.add(user_id)
    await query.answer()
    await query.message.reply_text("✍ Напишіть своє повідомлення для підтримки, і я передам його адміну.")

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    text = update.message.text

    if user_id in support_mode_users:
        # Відправка адміну
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Нове повідомлення від користувача:\n"
                 f"👤 {username} (ID: {user_id})\n\n"
                 f"💬 {text}"
        )
        await update.message.reply_text("✅ Ваше повідомлення відправлено в підтримку.")
        support_mode_users.remove(user_id)
    else:
        await find_movie(update, context)

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

# ===== Збереження статистики =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

# ===== Запуск бота =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message))

    print("Бот запущений...")
    app.run_polling()
