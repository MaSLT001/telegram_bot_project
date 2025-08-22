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
        [InlineKeyboardButton("🎁 Розіграш Мегого", callback_data="raffle")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all"),
            InlineKeyboardButton("🎁 Учасники розіграшу", callback_data="raffle_participants")
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
    film = movies.get(code)
    if not film:
        film = find_film_by_text(code)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))
        return
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    if last_film_message_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=last_film_message_id, reply_markup=None)
        except:
            pass
    msg = await message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text, update.effective_user.id == ADMIN_ID))
    last_film_message_id = msg.message_id

# ===== Random film =====
async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update, context, code)
    await update.callback_query.answer()

# ===== Статистика =====
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    total_users = len(user_stats)
    await update.callback_query.edit_message_text(f"📊 Користувачів: {total_users}", reply_markup=main_keyboard(True))

# ===== Розіграш =====
scheduler = AsyncIOScheduler()

async def monthly_raffle(context):
    participants = [u for u, info in user_stats.items() if info.get("raffle_participation")]
    if not participants:
        print("🎁 Немає учасників розіграшу цього місяця")
        return
    winner_id = random.choice(participants)
    user_stats[winner_id]["raffle_participation_won"] = True
    save_stats()
    try:
        await context.bot.send_message(int(winner_id),
            "🏆 Вітаємо! Ви виграли розіграш Мегого цього місяця! Напишіть нам у підтримку, щоб отримати приз."
        )
    except:
        pass
    try:
        winner_info = user_stats[winner_id]
        await context.bot.send_message(ADMIN_ID,
            f"🎉 Розіграш завершено! Переможець: {winner_info['first_name']} (@{winner_info.get('username','')})"
        )
    except:
        pass
    for u in participants:
        user_stats[u]["raffle_participation"] = False
    save_stats()
    print("✅ Розіграш оновлено для нового місяця")

def start_scheduler(app):
    scheduler.add_job(lambda: asyncio.create_task(monthly_raffle(app)), 'cron', day=1, hour=0, minute=0)
    scheduler.start()

# ===== Підтримка =====
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Звернення", callback_data="support_ticket")],
        [InlineKeyboardButton("🤝 Співпраця", callback_data="support_collab")],
        [InlineKeyboardButton("🎁 Повідомити про перемогу", callback_data="support_raffle")]
    ])
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Виберіть тип повідомлення:", reply_markup=keyboard)

async def support_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "support_ticket":
        context.user_data['support_ticket'] = True
    elif query.data == "support_collab":
        context.user_data['support_collab'] = True
    elif query.data == "support_raffle":
        context.user_data['support_raffle'] = True
    await query.answer()
    await query.message.reply_text("✉️ Напишіть своє повідомлення:")

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    if context.user_data.get('support_raffle'):
        context.user_data['support_raffle'] = False
        if user_stats.get(str(user.id), {}).get("raffle_participation_won"):
            await update.message.reply_text("✅ Вітаємо! Вашу перемогу підтверджено. Ви можете отримати приз.")
        else:
            await update.message.reply_text("❌ Ви не є переможцем цього місяця.")
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Відповісти", callback_data=f"reply_{user.id}")]])
    await context.bot.send_message(ADMIN_ID, f"📩 Нове звернення від {user.first_name} (@{user.username}):\n\n{text}", reply_markup=keyboard)
    await update.message.reply_text("✅ Ваше повідомлення надіслано у підтримку.")

async def participate_in_raffle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in user_stats and not user_stats[uid].get("raffle_participation"):
        user_stats[uid]["raffle_participation"] = True
        save_stats()
        await update.callback_query.answer("🎉 Ви успішно взяли участь у розіграші!")
        await update.callback_query.message.edit_reply_markup(reply_markup=None)
    else:
        await update.callback_query.answer("❌ Ви вже берете участь або не знайдені в статистиці.")

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": user.username, "first_name": user.first_name}
        save_stats()
    await update.message.reply_text(f"Привіт, {user.first_name}!👋 Введи назву фільму або його код, також можеш натиснути кнопку нижче щоб ми тобі запропонували фільм😉",
        reply_markup=main_keyboard(user.id == ADMIN_ID))

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
        save_stats()
    if context.user_data.get('support_ticket') or context.user_data.get('support_collab') or context.user_data.get('support_raffle'):
        await handle_support_message(update, context)
        return
    await show_film(update, context, code)

# ===== Main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code))
    app.add_handler(CallbackQueryHandler(random_film, pattern="random_film"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="support"))
    app.add_handler(CallbackQueryHandler(support_button_callback, pattern="support_"))
    app.add_handler(CallbackQueryHandler(participate_in_raffle, pattern="participate_raffle"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="stats"))

    start_scheduler(app)
    print("✅ Бот запущений")
    asyncio.run(app.run_polling())

if __name__ == "__main__":
    main()
