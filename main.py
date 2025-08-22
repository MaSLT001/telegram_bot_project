import os
import json
import random
import asyncio
import nest_asyncio
from datetime import datetime
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
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
        [InlineKeyboardButton("🎁 Розіграш MEGOGO", callback_data="raffle")]
    ]
    buttons.append([InlineKeyboardButton("✉️ Підтримка", callback_data="support")])
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
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all"),
            InlineKeyboardButton("🎁 Учасники розіграшу", callback_data="raffle_participants")
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
last_film_message = None  # Для видалення старих кнопок

async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    global last_film_message
    film = movies.get(code)
    if not film:
        film = find_film_by_text(code)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))
        return
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    if last_film_message:
        try:
            await last_film_message.edit_reply_markup(reply_markup=None)
        except:
            pass
    last_film_message = await message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text, update.effective_user.id == ADMIN_ID))

# ===== Рандомний фільм =====
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
async def raffle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = get_message(update)
    await message.reply_text(
        "🎁 Розіграш місячної підписки MEGOGO!\n\nНатисніть кнопку нижче щоб взяти участь.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Взяти участь", callback_data="raffle_join")]])
    )

async def raffle_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    user_stats[uid]["raffle"] = True
    save_stats()
    await update.callback_query.answer("✅ Ви стали учасником розіграшу!")
    await update.callback_query.edit_message_text("✅ Ви стали учасником розіграшу!")

async def show_raffle_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    participants = [u for u,v in user_stats.items() if v.get("raffle")]
    if not participants:
        text = "❌ Немає учасників розіграшу"
    else:
        text = "🎁 Учасники розіграшу:\n\n" + "\n".join(
            [f"{user_stats[u]['first_name']} (@{user_stats[u].get('username','')})" for u in participants]
        )
    await update.callback_query.edit_message_text(text, reply_markup=main_keyboard(True))

async def raffle_job(app: Bot):
    participants = [u for u,v in user_stats.items() if v.get("raffle")]
    if not participants:
        print("Немає учасників для розіграшу")
        await app.send_message(ADMIN_ID, "⚠️ Розіграш місячної підписки не проведено – немає учасників.")
        return

    winner_id = random.choice(participants)
    winner = user_stats[winner_id]

    # Повідомлення переможцю
    try:
        await app.send_message(int(winner_id), "🎉 Вітаємо! Ви виграли місячну підписку MEGOGO! Напишіть у підтримку, щоб отримати приз.")
    except:
        pass

    # Повідомлення іншим учасникам
    for uid in participants:
        if uid != winner_id:
            try:
                await app.send_message(int(uid), "❌ Розіграш завершено – на цей раз ви не виграли, спробуйте наступного місяця!")
            except:
                pass

    # Лог адміну
    await app.send_message(int(ADMIN_ID), f"🏆 Розіграш завершено. Переможець: {winner['first_name']} (@{winner.get('username','')})")

    # Очищення учасників
    for u in participants:
        user_stats[u]["raffle"] = False
    save_stats()

    print(f"Розіграш проведено. Переможець: {winner['first_name']} (@{winner.get('username','')})")

async def schedule_raffle(app: Bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(raffle_job(app)), "cron", day=1, hour=0, minute=0)
    scheduler.start()

# ===== Підтримка =====
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Виберіть тип повідомлення:", reply_markup=support_keyboard()
    )

# ===== Start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
        save_stats()
    await update.message.reply_text(
        "Вітаю! Оберіть дію:", reply_markup=main_keyboard(update.effective_user.id==ADMIN_ID)
    )

# ===== Обробники =====
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "random_film":
        await random_film(update, context)
    elif data == "raffle":
        await raffle_start(update, context)
    elif data == "raffle_join":
        await raffle_join(update, context)
    elif data == "raffle_participants":
        await show_raffle_participants(update, context)
    elif data == "support":
        await support_callback(update, context)
    elif data.startswith("support"):
        await update.callback_query.answer("Відправте повідомлення в чат підтримки")
    elif data == "stats":
        await show_stats(update, context)
    else:
        await update.callback_query.answer()

# ===== MAIN =====
async def main_async():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Запуск розіграшу
    await schedule_raffle(app.bot)

    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main_async())
