import os
import json
import random
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
    uid = str(user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": user.username, "first_name": user.first_name}
        save_stats()
    await update.message.reply_text(
        f"Привіт, {user.first_name}!👋 Введи код фільму або натисни кнопку нижче щоб ми тобі запропонували фільм😉",
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

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    await show_film(update, context, code)

# ===== Підтримка =====
pending_broadcasts = {}
support_mode_users = set()
reply_mode_admin = {}

async def support_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    support_mode_users.add(user_id)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("✍ Напишіть повідомлення для підтримки, і я передам його адміну.")

async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Адмін відповідає
    if user_id == ADMIN_ID and user_id in reply_mode_admin:
        target_id = reply_mode_admin[user_id]
        try:
            await context.bot.send_message(chat_id=target_id, text=f"📩 Відповідь від підтримки:\n{text}")
            await update.message.reply_text("✅ Відправлено користувачу")
        except:
            await update.message.reply_text("❌ Не вдалося відправити повідомлення")
        return

    # Користувач пише в підтримку
    if user_id in support_mode_users:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Нове повідомлення від @{update.effective_user.username} ({user_id}):\n{text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏ Відповісти", callback_data=f"reply_{user_id}")]
            ])
        )
        await update.message.reply_text("✅ Ваше повідомлення відправлено в підтримку.")
        support_mode_users.remove(user_id)
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

# ===== Розсилка =====
async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠ Використання: /sendall <текст>")
        return
    pending_broadcasts[ADMIN_ID] = " ".join(context.args)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Підтвердити", callback_data="confirm_sendall"),
         InlineKeyboardButton("❌ Скасувати", callback_data="cancel_sendall")]
    ])
    await update.message.reply_text(f"📢 Надіслати {len(user_stats)} користувачам:\n{pending_broadcasts[ADMIN_ID]}", reply_markup=keyboard)

async def confirm_sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID or ADMIN_ID not in pending_broadcasts:
        return
    text_to_send = pending_broadcasts.pop(ADMIN_ID)
    users = list(user_stats.keys())
    total = len(users)
    success = fail = 0
    removed_users = []
    progress_msg = await query.message.reply_text(f"🚀 Починаю розсилку...\n0 / {total}")
    for idx, uid in enumerate(users, start=1):
        try:
            await context.bot.send_message(chat_id=uid, text=text_to_send)
            success += 1
        except:
            fail += 1
            removed_users.append(uid)
            user_stats.pop(uid, None)
        if idx % 10 == 0 or idx == total:
            await progress_msg.edit_text(f"🚀 Розсилка...\n✅ {success} / {idx}\n⚠ {fail} помилок")
    save_stats()
    await progress_msg.edit_text(f"🎉 Розсилка завершена!\n✅ {success}\n⚠ {fail}\n🗑 Видалено: {len(removed_users)}")

async def cancel_sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    if ADMIN_ID in pending_broadcasts:
        pending_broadcasts.pop(ADMIN_ID)
    await query.message.reply_text("🚫 Розсилка скасована")

# ===== Main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("stopreply", stop_reply))
    app.add_handler(CommandHandler("sendall", sendall))

    # Callback
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    app.add_handler(CallbackQueryHandler(support_button, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(reply_callback, pattern="^reply_"))
    app.add_handler(CallbackQueryHandler(confirm_sendall, pattern="^confirm_sendall$"))
    app.add_handler(CallbackQueryHandler(cancel_sendall, pattern="^cancel_sendall$"))

    # Повідомлення
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support))

    print("✅ Бот запущений")
    app.run_polling()

if __name__ == "__main__":
    main()

