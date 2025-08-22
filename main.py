import os
import json
import random
import asyncio
from datetime import datetime
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from deep_translator import GoogleTranslator
from difflib import get_close_matches
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===== ENV змінні =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")

if not TOKEN or not ADMIN_ID or not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
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

GIVEAWAY_WINNER_KEY = "giveaway_winner"
GIVEAWAY_PARTICIPANT_KEY = "giveaway_participant"

# ===== GitHub save =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, indent=2, ensure_ascii=False)
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_user(GITHUB_OWNER).get_repo(GITHUB_REPO)
        content = json.dumps(user_stats, indent=2, ensure_ascii=False)
        try:
            file = repo.get_contents(STATS_FILE)
            repo.update_file(path=STATS_FILE, message="Update stats.json", content=content, sha=file.sha)
        except:
            repo.create_file(path=STATS_FILE, message="Create stats.json", content=content)
    except Exception as e:
        print("❌ Помилка при збереженні на GitHub:", e)

# ===== Клавіатури =====
def main_keyboard(is_admin=False):
    buttons = [
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")],
        [InlineKeyboardButton("🎁 Розіграш", callback_data="giveaway")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📋 Учасники розіграшу", callback_data="giveaway_participants"),
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all")
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
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all")
        ])
    return InlineKeyboardMarkup(buttons)

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
last_film_message_id = None

async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    global last_film_message_id
    film = movies.get(code) or find_film_by_text(code)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))
        return
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    sent = await message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text, update.effective_user.id == ADMIN_ID))
    # видаляємо кнопки з попереднього
    if last_film_message_id and last_film_message_id != sent.message_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=message.chat_id, message_id=last_film_message_id, reply_markup=None)
        except:
            pass
    last_film_message_id = sent.message_id

async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update, context, code)
    await update.callback_query.answer()

# ===== Розіграш =====
async def giveaway_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    user_stats[uid][GIVEAWAY_PARTICIPANT_KEY] = True
    save_stats()
    await update.callback_query.answer("✅ Ви взяли участь у розіграші")
    await update.callback_query.message.reply_text("🎁 Ви успішно зареєстровані в розіграші!")

async def show_giveaway_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    participants = [u for u in user_stats if user_stats[u].get(GIVEAWAY_PARTICIPANT_KEY)]
    if not participants:
        text = "❌ Немає учасників розіграшу"
    else:
        text = "🎁 Учасники розіграшу:\n\n" + "\n".join([
            f"{user_stats[u]['first_name']} (@{user_stats[u].get('username',''))}" for u in participants
        ])
    await update.callback_query.edit_message_text(text, reply_markup=main_keyboard(True))

def select_giveaway_winner(context: ContextTypes.DEFAULT_TYPE):
    participants = [u for u in user_stats if user_stats[u].get(GIVEAWAY_PARTICIPANT_KEY)]
    if not participants:
        return
    winner_uid = random.choice(participants)
    for u in user_stats:
        user_stats[u][GIVEAWAY_WINNER_KEY] = (u == winner_uid)
    save_stats()
    # відправка повідомлення переможцю
    asyncio.create_task(context.bot.send_message(
        int(winner_uid),
        "🏆 Вітаємо! Ви перемогли у розіграші місячної підписки на MEGOGO. Напишіть у підтримку, щоб отримати приз."
    ))
    asyncio.create_task(context.bot.send_message(
        ADMIN_ID,
        f"🏆 Переможець розіграшу: {user_stats[winner_uid]['first_name']} (@{user_stats[winner_uid].get('username')})"
    ))

# ===== Підтримка =====
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['support'] = True
    await update.callback_query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Звернення", callback_data="support_ticket")],
        [InlineKeyboardButton("🤝 Співпраця", callback_data="support_collab")],
        [InlineKeyboardButton("🏆 Повідомити про перемогу", callback_data="support_win")],
    ])
    await update.callback_query.message.reply_text(
        "Виберіть варіант повідомлення для підтримки:", reply_markup=keyboard
    )

async def handle_support_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    if query.data == "support_ticket":
        context.user_data['support_type'] = "ticket"
        await query.message.reply_text("✉️ Напишіть ваше звернення:")
    elif query.data == "support_collab":
        context.user_data['support_type'] = "collab"
        await query.message.reply_text("🤝 Напишіть пропозицію для співпраці:")
    elif query.data == "support_win":
        if user_stats.get(uid, {}).get(GIVEAWAY_WINNER_KEY):
            context.user_data['support_type'] = "win"
            await query.message.reply_text("🏆 Ви перемогли! Напишіть повідомлення для отримання призу.")
        else:
            await query.message.reply_text("❌ Ви не є переможцем розіграшу.")
    await query.answer()

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if 'support_type' not in context.user_data:
        return
    text = update.message.text
    support_type = context.user_data.pop('support_type')
    if support_type == "win":
        await update.message.reply_text("✅ Ваше повідомлення отримано. Адмін перевірить його.")
        await context.bot.send_message(
            ADMIN_ID,
            f"🏆 Переможець {user_stats[uid]['first_name']} (@{user_stats[uid].get('username')}) звернувся для отримання призу:\n\n{text}"
        )
    else:
        await update.message.reply_text("✅ Ваше повідомлення надіслано у підтримку.")
        await context.bot.send_message(
            ADMIN_ID,
            f"📩 Нове повідомлення від {update.effective_user.first_name} (@{update.effective_user.username}) [{support_type}]:\n\n{text}"
        )

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": user.username, "first_name": user.first_name}
        save_stats()
    await update.message.reply_text(
        f"Привіт, {user.first_name}!👋 Введи назву фільму або його код, також можеш натиснути кнопку нижче щоб ми тобі запропонували фільм😉",
        reply_markup=main_keyboard(user.id == ADMIN_ID)
    )
    # повідомлення про розіграш тим, хто ще не брав участь
    if not user_stats[uid].get(GIVEAWAY_PARTICIPANT_KEY):
        await update.message.reply_text(
            "🎁 Розіграш місячної підписки на MEGOGO! Натисніть '🎁 Розіграш', щоб взяти участь."
        )

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    save_stats()
    if context.user_data.get('support_type'):
        await handle_support_message(update, context)
        return
    await show_film(update, context, update.message.text.strip())

# ===== Main =====
async def main_async():
    app = ApplicationBuilder().token(TOKEN).build()

    # Command and message handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code))
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    app.add_handler(CallbackQueryHandler(giveaway_callback, pattern="^giveaway$"))
    app.add_handler(CallbackQueryHandler(show_giveaway_participants, pattern="^giveaway_participants$"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(handle_support_options, pattern="^support_"))
    
    # Scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(select_giveaway_winner, "cron", day=1, hour=0, minute=0, args=[app])
    scheduler.start()

    print("✅ Бот запущений")
    await app.run_polling()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
