import os
import json
import random
import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ===== Параметри =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN or not ADMIN_ID or not DATABASE_URL:
    raise ValueError("BOT_TOKEN, ADMIN_ID або DATABASE_URL не встановлені.")

support_mode_users = set()
reply_mode_admin = {}  # {admin_id: user_id_to_reply}

# ===== Завантаження фільмів =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

# ===== Клавіатури =====
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ])

def get_film_keyboard(share_text):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Поділитися", switch_inline_query=share_text),
         InlineKeyboardButton("💬 Підтримка", callback_data="support")]
    ])

# ===== База даних =====
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id BIGINT PRIMARY KEY,
            name TEXT,
            visits INT
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            message TEXT,
            answered BOOLEAN DEFAULT FALSE,
            admin_reply TEXT,
            created_at TIMESTAMP DEFAULT now()
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id SERIAL PRIMARY KEY,
            message TEXT,
            sent_at TIMESTAMP DEFAULT now()
        );
    """)
    await conn.close()

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.full_name

    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT visits FROM user_stats WHERE user_id=$1;", user_id)
    if row:
        visits = row['visits'] + 1
        await conn.execute("UPDATE user_stats SET visits=$1, name=$2 WHERE user_id=$3;", visits, user_name, user_id)
    else:
        visits = 1
        await conn.execute("INSERT INTO user_stats(user_id, name, visits) VALUES($1,$2,$3);", user_id, user_name, visits)
    await conn.close()

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
        text, parse_mode="Markdown", reply_markup=get_film_keyboard(text)
    )
    await query.answer()

async def find_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=get_film_keyboard(text)
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

    if user_id == ADMIN_ID and user_id in reply_mode_admin:
        target_user_id = reply_mode_admin[user_id]
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("""
            UPDATE support_messages
            SET answered = TRUE, admin_reply = $1
            WHERE user_id = $2 AND answered = FALSE
        """, text, target_user_id)
        await conn.close()

        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"📩 Відповідь від підтримки:\n\n{text}")
            await update.message.reply_text("✅ Повідомлення відправлено користувачу.")
        except:
            await update.message.reply_text("⚠ Не вдалося відправити повідомлення користувачу.")
        return

    if user_id in support_mode_users:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO support_messages(user_id, username, message) VALUES($1,$2,$3);",
            user_id, username, text
        )
        await conn.close()

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

# ===== Розсилка =====
async def broadcast(context: ContextTypes.DEFAULT_TYPE, text: str):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT user_id FROM user_stats;")
    await conn.execute("INSERT INTO broadcasts(message) VALUES($1);", text)
    await conn.close()

    for row in rows:
        try:
            await context.bot.send_message(chat_id=row['user_id'], text=text)
        except Exception as e:
            print(f"Не вдалося відправити користувачу {row['user_id']}: {e}")

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
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT * FROM user_stats;")
    await conn.close()
    if not rows:
        await update.message.reply_text("Статистика порожня.")
        return
    text = "📊 Статистика користувачів:\n\n"
    for row in rows:
        text += f"👤 {row['name']} (ID: {row['user_id']}) — відвідувань: {row['visits']}\n"
    await update.message.reply_text(text)

# ===== Запуск =====
if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CommandHandler("stopreply", stop_reply))

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_support_message))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), find_movie))

    app.add_handler(CallbackQueryHandler(random_film_callback, pattern="random_film"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="support"))
    app.add_handler(CallbackQueryHandler(reply_callback, pattern="reply_"))

    print("Бот запущено...")
    app.run_polling()
