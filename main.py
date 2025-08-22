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

# ===== Статистика =====
STATS_FILE = "stats.json"
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        user_stats = json.load(f)
else:
    user_stats = {}

# ===== Підтримка =====
SUPPORT_FILE = "support.json"
if os.path.exists(SUPPORT_FILE):
    with open(SUPPORT_FILE, "r", encoding="utf-8") as f:
        support_requests = json.load(f)
else:
    support_requests = {}

# ===== GitHub save =====
def save_stats_to_github():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, indent=2, ensure_ascii=False)
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_user(GITHUB_OWNER).get_repo(GITHUB_REPO)
        content = json.dumps(user_stats, indent=2, ensure_ascii=False)
        try:
            file = repo.get_contents(STATS_FILE)
            repo.update_file(STATS_FILE, "Update stats.json", content, file.sha)
        except Exception:
            repo.create_file(STATS_FILE, "Create stats.json", content)
    except Exception as e:
        print("❌ Помилка GitHub:", e)

# ===== Клавіатури =====
def main_keyboard(is_admin=False):
    buttons = [
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")],
        [InlineKeyboardButton("🎁 Розіграш MEGOGO", callback_data="raffle")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
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
        buttons.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
    return InlineKeyboardMarkup(buttons)

def support_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Звернення", callback_data="support_zvernennya")],
        [InlineKeyboardButton("🤝 Співпраця", callback_data="support_spivpratsya")],
        [InlineKeyboardButton("🏆 Повідомити про перемогу", callback_data="support_peremoga")]
    ])

# ===== Допоміжна =====
def get_message(update: Update):
    return update.message or update.callback_query.message

# ===== Пошук фільму =====
def find_film_by_text(text):
    if text in movies:
        return movies[text]

    try:
        translated = GoogleTranslator(source='auto', target='uk').translate(text)
    except:
        translated = text

    translated_lower = translated.lower()
    for film in movies.values():
        if film['title'].lower() == translated_lower:
            return film
    for film in movies.values():
        if translated_lower in film['title'].lower():
            return film
    titles = [f['title'] for f in movies.values()]
    matches = get_close_matches(translated, titles, n=1, cutoff=0.5)
    if matches:
        return next(f for f in movies.values() if f['title'] == matches[0])
    return None

# ===== Показ фільму =====
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code_or_text: str):
    film = find_film_by_text(code_or_text)
    message = get_message(update)

    if not film:
        await message.reply_text(
            "❌ Фільм не знайдено",
            reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID)
        )
        return

    last_msg = context.user_data.get("last_film_message")
    text = f"🎬 {film['title']}\n\n{film['desc']}\n\n🔗 {film['link']}"

    if last_msg:
        try:
            await last_msg.edit_reply_markup(reply_markup=None)
        except:
            pass

    sent = await message.reply_text(
        text,
        reply_markup=film_keyboard(film['title'], update.effective_user.id == ADMIN_ID)
    )
    context.user_data["last_film_message"] = sent

# ===== Рандомний фільм =====
async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await get_message(update).reply_text("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update, context, code)

# ===== Обробники =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Привіт, {user.first_name}! 👋 Введи назву фільму або натисни кнопку нижче.",
        reply_markup=main_keyboard(user.id == ADMIN_ID)
    )

async def raffle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_message(update).reply_text("🎁 Розіграш MEGOGO! Деталі поки відсутні.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = len(user_stats)
    total_requests = sum(user_stats.values())
    await get_message(update).reply_text(
        f"📊 Статистика бота:\nКористувачів: {total_users}\nЗапитів: {total_requests}"
    )

# ===== Підтримка з темами =====
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_message(update).reply_text(
        "Виберіть тему звернення:",
        reply_markup=support_keyboard()
    )

async def support_topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["support_topic"] = query.data
    context.user_data["awaiting_support"] = True
    await query.message.reply_text("✉️ Введіть ваше повідомлення для підтримки:")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "немає"
    text = update.message.text

    # Якщо користувач пише звернення
    if context.user_data.get("awaiting_support"):
        topic = context.user_data.get("support_topic", "support")
        # Зберігаємо у файл
        support_requests.setdefault(str(user_id), []).append({
            "topic": topic,
            "message": text
        })
        with open(SUPPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(support_requests, f, indent=2, ensure_ascii=False)

        # Повідомлення користувачу
        await update.message.reply_text(
            "✅ Ваше повідомлення відправлено в підтримку!"
        )

        # Повідомлення адміністратору
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✉️ Нове повідомлення у підтримку\n\n"
                 f"👤 Від: @{username}\n"
                 f"🆔 ID: {user_id}\n"
                 f"📂 Розділ: {topic}\n\n"
                 f"📨 Текст:\n{text}"
        )

        context.user_data["awaiting_support"] = False
        context.user_data["support_topic"] = None
        return

    # Якщо це не звернення – обробляємо як пошук фільму
    await show_film(update, context, text)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "random_film":
        await random_film(update, context)
    elif query.data == "raffle":
        await raffle(update, context)
    elif query.data == "support":
        await support(update, context)
    elif query.data.startswith("support_"):
        await support_topic_handler(update, context)
    elif query.data == "stats" and update.effective_user.id == ADMIN_ID:
        await stats(update, context)

# ===== MAIN =====
async def main_async():
    app = ApplicationBuilder().token(TOKEN).build()
    await app.bot.delete_webhook(drop_pending_updates=True)

    # Command
    app.add_handler(CommandHandler("start", start))
    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_handler))
    # Text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    scheduler = AsyncIOScheduler()
    scheduler.start()

    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async())
