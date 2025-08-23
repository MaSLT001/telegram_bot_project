import os
import json
import random
import asyncio
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from deep_translator import GoogleTranslator
from difflib import get_close_matches
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ===== ENV змінні =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")

for var in [TOKEN, ADMIN_ID, GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]:
    if not var:
        raise ValueError("❌ Перевірте, що всі змінні оточення встановлені")

# ===== Фільми =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

normalized_titles = {f['title'].lower(): code for code, f in movies.items()}

# ===== Кеш перекладів =====
translation_cache = {}

async def translate_async(text, target='uk'):
    if text in translation_cache:
        return translation_cache[text]
    loop = asyncio.get_event_loop()
    translated = await loop.run_in_executor(None, lambda: GoogleTranslator(source='auto', target=target).translate(text))
    translation_cache[text] = translated
    return translated

# ===== Статистика =====
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}

SUPPORT_FILE = "support.json"
if os.path.exists(SUPPORT_FILE):
    with open(SUPPORT_FILE, "r", encoding="utf-8") as f:
        support_requests = json.load(f)
else:
    support_requests = {}

# ===== Збереження статистики =====
async def save_user_stats_async():
    content = json.dumps(user_stats, indent=2, ensure_ascii=False)
    await asyncio.to_thread(lambda: open(STATS_FILE, "w", encoding="utf-8").write(content))
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_user(GITHUB_OWNER).get_repo(GITHUB_REPO)
        try:
            file = repo.get_contents(STATS_FILE)
            repo.update_file(STATS_FILE, "Update stats.json", content, file.sha)
        except Exception:
            repo.create_file(STATS_FILE, "Create stats.json", content)
    except Exception as e:
        print("❌ Помилка GitHub:", e)

def update_user_stats(user):
    user_id = str(user.id)
    if user_id not in user_stats:
        user_stats[user_id] = {
            "username": user.username or "немає",
            "first_name": user.first_name or "немає",
            "raffle": False
        }
    asyncio.create_task(save_user_stats_async())

def is_raffle_active():
    return any(u.get("raffle") for u in user_stats.values())

# ===== Клавіатури =====
def main_keyboard(is_admin=False):
    raffle_text = "🎁 Розіграш MEGOGO"
    if is_raffle_active():
        raffle_text += " (активний)"
    buttons = [
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")],
        [InlineKeyboardButton(raffle_text, callback_data="raffle")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
        buttons.append([InlineKeyboardButton("👥 Учасники розіграшу", callback_data="raffle_participants")])
        buttons.append([InlineKeyboardButton("📢 Розсилка", callback_data="broadcast")])
    return InlineKeyboardMarkup(buttons)

def film_keyboard(film_title, is_admin=False):
    buttons = [
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=film_title),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
        ],
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
    return InlineKeyboardMarkup(buttons)

def support_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Звернення", callback_data="support_zvernennya")],
        [InlineKeyboardButton("🤝 Співпраця", callback_data="support_spivpratsya")],
        [InlineKeyboardButton("🏆 Повідомити про перемогу", callback_data="support_peremoga")]
    ])

def admin_reply_keyboard(user_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton("💬 Відповісти", callback_data=f"reply_{user_id}")]])

def winner_keyboard():
    return support_keyboard()

def get_message(update: Update):
    return update.message or update.callback_query.message

# ===== Пошук фільму =====
async def find_film_by_text(text):
    if text in movies:
        return movies[text]
    translated = await translate_async(text)
    t_lower = translated.lower()
    if t_lower in normalized_titles:
        return movies[normalized_titles[t_lower]]
    for f in movies.values():
        if t_lower in f['title'].lower():
            return f
    titles = [f['title'] for f in movies.values()]
    matches = get_close_matches(translated, titles, n=1, cutoff=0.5)
    if matches:
        return next(f for f in movies.values() if f['title'] == matches[0])
    return None

# ===== Показ фільму =====
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code_or_text: str):
    user = update.effective_user
    update_user_stats(user)
    film = await find_film_by_text(code_or_text)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(user.id == ADMIN_ID))
        return
    last_msg = context.user_data.get("last_film_message")
    text = f"🎬 {film['title']}\n\n{film['desc']}\n\n🔗 {film['link']}"
    if last_msg:
        try:
            await last_msg.edit_reply_markup(reply_markup=None)
        except: pass
    sent = await message.reply_text(text, reply_markup=film_keyboard(film['title'], user.id == ADMIN_ID))
    context.user_data["last_film_message"] = sent

# ===== Рандомний фільм =====
async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await get_message(update).reply_text("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update, context, code)

# ===== Старт =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_stats(user)
    await update.message.reply_text(
        f"Привіт, {user.first_name}! 👋 Введи код або назву фільму, також нижче є кнопка рандомного фільму.",
        reply_markup=main_keyboard(user.id == ADMIN_ID)
    )

# ===== Текстовий хендлер =====
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_stats(user)
    text = update.message.text if update.message else ""
    await show_film(update, context, text)

# ===== Розіграш =====
async def raffle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_stats(user)
    message = get_message(update)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Взяти участь", callback_data="raffle_join")]])
    await message.reply_text(
        "🎁 Розіграш MEGOGO!\n\nНатисніть кнопку нижче, щоб взяти участь у розіграші максимальної підписки.",
        reply_markup=keyboard
    )

async def raffle_join_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    user_stats[user_id]["raffle"] = True
    await save_user_stats_async()
    await query.message.edit_text("✅ Ви успішно взяли участь у розіграші MEGOGO!")

# ===== Callback handler =====
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "random_film":
        await random_film(update, context)
    elif data == "raffle":
        await raffle(update, context)
    elif data == "raffle_join":
        await raffle_join_handler(update, context)

# ===== MAIN =====
async def main_async():
    app = ApplicationBuilder().token(TOKEN).build()
    await app.bot.delete_webhook(drop_pending_updates=True)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    scheduler = AsyncIOScheduler()
    scheduler.start()

    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async())
