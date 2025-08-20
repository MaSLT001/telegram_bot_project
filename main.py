import os
import json
import random
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ===== ENV перемінні =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("BOT_TOKEN не встановлено")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID не встановлено")

ADMIN_ID = int(ADMIN_ID)

# ===== БАЗА ДАНИХ =====
DB_FILE = "stats.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT
    )
    """)
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    INSERT OR IGNORE INTO users (id, username, first_name)
    VALUES (?, ?, ?)
    """, (user_id, username, first_name))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows

def get_all_users_info():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, username, first_name FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows

# ===== Фільми =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except:
    movies = {}

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
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    if code not in movies:
        await update.message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard())
        return
    film = movies[code]
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
    add_user(user.id, user.username, user.first_name)

    await update.message.reply_text(
        f"Привіт, {user.first_name}!👋 Введи код фільму або натисни кнопку нижче щоб ми тобі запропонували фільм😉",
        reply_markup=main_keyboard()
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    users = get_all_users_info()
    total = len(users)
    users_list = "\n".join(
        [f"{uid} — @{username or 'нема'} ({first_name or ''})" for uid, username, first_name in users]
    )
    text = f"📊 Всього користувачів: {total}\n\n{users_list}"
    await update.message.reply_text(text if len(text) < 4000 else f"📊 Всього користувачів: {total}")

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    await show_film(update, context, code)

# ===== Підтримка =====
pending_broadcasts = {}
support_mode_users = set()
reply_mode_admin = {}

async def support_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    add_user(user_id, update.callback_query.from_user.username, update.callback_query.from_user.first_name)
    support_mode_users.add(user_id)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("✍ Напишіть повідомлення для підтримки, і я передам його адміну.")

async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    text = update.message.text

    # Якщо адмін пише — розсилка всім
    if user.id == ADMIN_ID:
        users = get_all_users()
        success, fail = 0, 0
        for uid in users:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 {text}")
                success += 1
            except:
                fail += 1
        await update.message.reply_text(f"✅ Розсилка завершена!\nУспішно: {success}\n❌ Помилок: {fail}")
        return

    # Користувач пише в підтримку
    if user.id in support_mode_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Нове повідомлення від @{user.username} ({user.id}):\n{text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏ Відповісти", callback_data=f"reply_{user.id}")]
            ])
        )
        await update.message.reply_text("✅ Ваше повідомлення відправлено в підтримку.")
        support_mode_users.remove(user.id)
    else:
        await movie_by_code(update, context)

async def reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query.data.startswith("reply_"):
        return
    target_id = int(query.data.split("_")[1])
    reply_mode_admin[ADMIN_ID] = target_id
    await query.answer()
    await query.message.reply_text("✍ Введіть повідомлення для користувача або /stopreply щоб вийти")

async def stop_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and ADMIN_ID in reply_mode_admin:
        del reply_mode_admin[ADMIN_ID]
        await update.message.reply_text("🚪 Вийшли з режиму відповіді")
    else:
        await update.message.reply_text("⚠ Ви не в режимі відповіді")

# ===== Main =====
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("stopreply", stop_reply))

    # Callback
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    app.add_handler(CallbackQueryHandler(support_button, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(reply_callback, pattern="^reply_"))

    # Повідомлення
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support))

    print("✅ Бот запущений")
    app.run_polling()

if __name__ == "__main__":
    main()
