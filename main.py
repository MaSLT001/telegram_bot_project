import os
import json
import random
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from deep_translator import GoogleTranslator
from difflib import get_close_matches

# ===== ENV змінні =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not TOKEN or not ADMIN_ID:
    raise ValueError("Перевірте, що всі змінні оточення встановлені")

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

# ===== Збереження =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, indent=2, ensure_ascii=False)

# ===== Клавіатури =====
def main_keyboard(is_admin=False):
    buttons = [
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")],
        [InlineKeyboardButton("🎁 Розіграш Мегого", callback_data="raffle")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("👥 Учасники розіграшу", callback_data="raffle_participants")
        ])
    return InlineKeyboardMarkup(buttons)

def film_keyboard(text, is_admin=False):
    buttons = [
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
        ],
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("👥 Учасники розіграшу", callback_data="raffle_participants")
        ])
    return InlineKeyboardMarkup(buttons)

def support_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Звернення", callback_data="support_request")],
        [InlineKeyboardButton("🤝 Співпраця", callback_data="support_collab")],
        [InlineKeyboardButton("🏆 Повідомити про перемогу", callback_data="support_winner")]
    ])

# ===== Допоміжна =====
def get_message(update: Update):
    return update.message or update.callback_query.message

# ===== Пошук фільму =====
def find_film_by_text(text):
    try:
        translated = GoogleTranslator(source='auto', target='uk').translate(text)
    except:
        translated = text
    for film in movies.values():
        if film['title'].lower() == translated.lower():
            return film
    titles = [f['title'] for f in movies.values()]
    matches = get_close_matches(translated, titles, n=1, cutoff=0.5)
    if matches:
        return next(f for f in movies.values() if f['title'] == matches[0])
    return None

# ===== Показ фільму =====
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    film = movies.get(code)
    if not film:
        film = find_film_by_text(code)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))
        return
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    # Видаляємо старі кнопки
    if update.callback_query:
        await update.callback_query.message.edit_reply_markup(reply_markup=None)
    await message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text, update.effective_user.id == ADMIN_ID))

async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update, context, code)
    await update.callback_query.answer()

# ===== Розіграш =====
async def participate_in_raffle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user_stats.setdefault(uid, {"username": update.effective_user.username, "first_name": update.effective_user.first_name})
    if user_stats[uid].get("raffle_participation"):
        await update.callback_query.answer("Ви вже берете участь!", show_alert=True)
        return
    user_stats[uid]["raffle_participation"] = True
    save_stats()
    await update.callback_query.answer("Ви успішно взяли участь у розіграші!")

async def show_raffle_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    participants = [u for u, info in user_stats.items() if info.get("raffle_participation")]
    text = "🎁 Учасники розіграшу:\n\n" + "\n".join([
        f"{user_stats[u]['first_name']} (@{user_stats[u].get('username','')})" for u in participants
    ])
    if not participants:
        text = "🎁 Немає учасників розіграшу"
    await update.callback_query.edit_message_text(text, reply_markup=main_keyboard(True))

# ===== Старт бота =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
        save_stats()
    await update.message.reply_text(
        f"Привіт, {update.effective_user.first_name}!👋 Введи назву фільму або його код, також можеш натиснути кнопку нижче щоб ми тобі запропонували фільм😉",
        reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID)
    )

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
        save_stats()
    await show_film(update, context, code)

# ===== Автовідправка розіграшу =====
async def announce_new_raffle(app):
    participants = [u for u, info in user_stats.items() if not info.get("raffle_participation")]
    if not participants:
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎉 Взяти участь", callback_data="participate_raffle")]
    ])
    for uid in participants:
        try:
            await app.bot.send_message(int(uid),
                "🎁 Стартує новий розіграш Мегого! Натисніть кнопку нижче, щоб взяти участь.",
                reply_markup=keyboard
            )
        except:
            pass

# ===== Scheduler =====
def start_scheduler(app):
    scheduler = AsyncIOScheduler()
    # Запуск розіграшу першого числа кожного місяця
    scheduler.add_job(lambda: asyncio.create_task(monthly_raffle(app)), 'cron', day=1, hour=0, minute=0)
    scheduler.start()

async def monthly_raffle(app):
    participants = [u for u, info in user_stats.items() if info.get("raffle_participation")]
    if not participants:
        print("🎁 Немає учасників розіграшу цього місяця")
        return
    winner_id = random.choice(participants)
    user_stats[winner_id]["raffle_participation_won"] = True
    save_stats()
    try:
        await app.bot.send_message(int(winner_id),
            "🏆 Вітаємо! Ви виграли розіграш Мегого цього місяця! Напишіть нам у підтримку, щоб отримати приз."
        )
    except:
        pass
    try:
        winner_info = user_stats[winner_id]
        await app.bot.send_message(ADMIN_ID,
            f"🎉 Розіграш завершено! Переможець: {winner_info['first_name']} (@{winner_info.get('username','')})"
        )
    except:
        pass
    # Скидаємо участь для нового місяця
    for u in user_stats:
        user_stats[u]["raffle_participation"] = False
    save_stats()
    await announce_new_raffle(app)
    print("✅ Розіграш оновлено для нового місяця")

# ===== Main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code))
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    app.add_handler(CallbackQueryHandler(participate_in_raffle, pattern="^participate_raffle$"))
    app.add_handler(CallbackQueryHandler(show_raffle_participants, pattern="^raffle_participants$"))
    
    start_scheduler(app)
    print("✅ Бот запущений")
    asyncio.run(app.run_polling())

if __name__ == "__main__":
    main()
