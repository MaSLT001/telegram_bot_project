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
        [InlineKeyboardButton("🎁 Розіграш", callback_data="lottery")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all"),
            InlineKeyboardButton("🏆 Учасники розіграшу", callback_data="lottery_participants")
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

def support_keyboard():
    buttons = [
        [InlineKeyboardButton("Звернення", callback_data="support_ticket")],
        [InlineKeyboardButton("Співпраця", callback_data="support_collab")],
        [InlineKeyboardButton("Повідомити про перемогу", callback_data="support_lottery_win")]
    ]
    return InlineKeyboardMarkup(buttons)

def lottery_keyboard(user_id):
    buttons = [[InlineKeyboardButton("Взяти участь", callback_data=f"join_lottery_{user_id}")]]
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
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    film = movies.get(code)
    if not film:
        film = find_film_by_text(code)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))
        return
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    # видалити старі кнопки (редагуємо попереднє повідомлення)
    if update.callback_query:
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text, update.effective_user.id == ADMIN_ID))

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
async def start_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # створюємо ключ для розіграшу, якщо його ще немає
    if "lottery" not in user_stats:
        user_stats["lottery"] = {"participants": [], "winner": None, "active": True}
    else:
        user_stats["lottery"]["active"] = True
        user_stats["lottery"]["winner"] = None
        user_stats["lottery"]["participants"] = []

    save_stats()
    # надсилаємо повідомлення всім користувачам, хто ще не брав участь
    for uid, info in user_stats.items():
        if uid == "lottery":
            continue
        if uid not in user_stats["lottery"]["participants"]:
            try:
                await context.bot.send_message(
                    int(uid),
                    "🎁 Починається новий розіграш Мегого! Натисніть кнопку нижче, щоб взяти участь.",
                    reply_markup=lottery_keyboard(uid)
                )
            except:
                pass
    await update.callback_query.answer("✅ Розіграш розпочато!")

async def join_lottery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(update.effective_user.id)
    if "lottery" not in user_stats:
        user_stats["lottery"] = {"participants": [], "winner": None, "active": True}
    if user_id not in user_stats["lottery"]["participants"]:
        user_stats["lottery"]["participants"].append(user_id)
        save_stats()
        await query.answer("✅ Ви приєдналися до розіграшу!")
        await query.edit_message_text("✅ Ви приєдналися до розіграшу!")
    else:
        await query.answer("ℹ️ Ви вже берете участь у розіграші.")

async def lottery_participants_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    participants = user_stats.get("lottery", {}).get("participants", [])
    if not participants:
        await update.callback_query.edit_message_text("❌ Учасників поки немає", reply_markup=main_keyboard(True))
        return
    text = "🎁 Учасники розіграшу:\n\n" + "\n".join(
        f"{user_stats[u]['first_name']} (@{user_stats[u].get('username',''))}" for u in participants
    )
    await update.callback_query.edit_message_text(text, reply_markup=main_keyboard(True))

# ===== Підтримка =====
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Виберіть тему:", reply_markup=support_keyboard()
    )

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": user.username, "first_name": user.first_name}
        save_stats()
    await update.message.reply_text(
        f"Привіт, {user.first_name}!👋 Введи назву фільму або його код, або натисни кнопку нижче щоб ми запропонували фільм😉",
        reply_markup=main_keyboard(user.id == ADMIN_ID)
    )

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    save_stats()
    await show_film(update, context, code)

# ===== Main =====
async def main_async():
    app = ApplicationBuilder().token(TOKEN).build()
    scheduler = AsyncIOScheduler()
    # розіграш 1 числа кожного місяця
    scheduler.add_job(lambda: asyncio.create_task(lottery_draw(app)), 'cron', day=1, hour=0, minute=0)
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code))
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(start_lottery, pattern="^lottery$"))
    app.add_handler(CallbackQueryHandler(join_lottery_callback, pattern="^join_lottery_"))
    app.add_handler(CallbackQueryHandler(lottery_participants_callback, pattern="^lottery_participants$"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))

    print("✅ Бот запущений")
    await app.run_polling()

async def lottery_draw(app):
    participants = user_stats.get("lottery", {}).get("participants", [])
    if not participants:
        return
    winner_id = random.choice(participants)
    user_stats["lottery"]["winner"] = winner_id
    user_stats["lottery"]["active"] = False
    save_stats()
    # повідомлення переможцю
    try:
        await app.bot.send_message(int(winner_id), "🏆 Ви виграли місячну максимальну підписку Мегого! Напишіть у підтримку, щоб отримати приз.")
        await app.bot.send_message(int(ADMIN_ID), f"🏆 Переможець розіграшу: {user_stats[winner_id]['first_name']} (@{user_stats[winner_id].get('username','')})")
    except:
        pass

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
