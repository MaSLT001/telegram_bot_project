import os
import json
import random
import asyncio
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from deep_translator import GoogleTranslator
from difflib import get_close_matches
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.helpers import escape_markdown

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
    film = movies.get(code) or find_film_by_text(code)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))
        return
    last_msg = context.user_data.get("last_film_message")
    text = f"🎬 *{escape_markdown(film['title'], version=2)}*\n\n{escape_markdown(film['desc'], version=2)}\n\n🔗 {film['link']}"
    if last_msg:
        try:
            await last_msg.edit_reply_markup(reply_markup=None)
        except:
            pass
    sent = await message.reply_text(text, parse_mode="MarkdownV2", reply_markup=film_keyboard(text, update.effective_user.id == ADMIN_ID))
    context.user_data["last_film_message"] = sent

# ===== Рандомний фільм =====
async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        if update.callback_query:
            await update.callback_query.answer("❌ Список фільмів порожній.")
        else:
            await update.message.reply_text("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update, context, code)
    if update.callback_query:
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
    save_stats_to_github()
    await update.callback_query.answer("✅ Ви стали учасником розіграшу!")
    await update.callback_query.edit_message_text("✅ Ви стали учасником розіграшу!")

# ===== Підтримка =====
CHOOSING_SECTION, TYPING_MESSAGE, WAITING_ADMIN_REPLY = range(3)
pending_replies = {}

async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Оберіть розділ підтримки:", reply_markup=support_keyboard())
    return CHOOSING_SECTION

async def choose_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    section = query.data.split("_")[1]
    context.user_data["support_section"] = section
    await query.message.reply_text("✍️ Напишіть своє повідомлення для підтримки:")
    return TYPING_MESSAGE

async def user_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    section = context.user_data.get("support_section", "невідомо")
    section_names = {"zvernennya": "📩 Звернення", "spivpratsya": "🤝 Співпраця", "peremoga": "🏆 Повідомити про перемогу"}
    section_text = section_names.get(section, "Невідомий розділ")
    keyboard = [[
        InlineKeyboardButton("Відповісти", callback_data=f"reply_{update.effective_user.id}"),
        InlineKeyboardButton("❌ Закрити діалог", callback_data=f"close_{update.effective_user.id}")
    ]]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"✉️ Нове повідомлення у підтримку\n\n"
            f"👤 Від: {update.effective_user.full_name} (@{update.effective_user.username})\n"
            f"🆔 ID: {update.effective_user.id}\n"
            f"📂 Розділ: {section_text}\n\n"
            f"📨 Текст: {text}"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ Ваше повідомлення передано в підтримку. Очікуйте відповіді.")
    context.user_data.pop("support_section", None)
    return ConversationHandler.END

async def admin_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[1])
    pending_replies[ADMIN_ID] = user_id
    await query.message.reply_text("✍️ Введіть повідомлення для користувача:")
    return WAITING_ADMIN_REPLY

async def admin_close_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Діалог закрито")
    user_id = int(query.data.split("_")[1])
    if ADMIN_ID in pending_replies and pending_replies[ADMIN_ID] == user_id:
        del pending_replies[ADMIN_ID]
    await query.message.reply_text("❌ Діалог із цим користувачем закрито.")

async def admin_reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        user_id = pending_replies.pop(ADMIN_ID, None)
        if user_id:
            await context.bot.send_message(chat_id=user_id, text=f"📩 Відповідь від підтримки:\n\n{update.message.text}")
            await update.message.reply_text("✅ Відповідь надіслана користувачу.")
    return ConversationHandler.END

# ===== Start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
        save_stats_to_github()
    first_name = update.effective_user.first_name or "друже"
    welcome_text = f"Привіт, {first_name}!👋\nВведи назву фільму або його код, також можеш натиснути кнопку нижче щоб ми тобі запропонували фільм😉"
    await update.message.reply_text(welcome_text, reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))

# ===== Callback Handler =====
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "random_film":
        await random_film(update, context)
    elif data == "raffle":
        await raffle_start(update, context)
    elif data == "raffle_join":
        await raffle_join(update, context)
    elif data == "support":
        await support_callback(update, context)
    elif data.startswith("support_"):
        await choose_section(update, context)
    elif data.startswith("reply_"):
        await admin_reply_button(update, context)
    elif data.startswith("close_"):
        await admin_close_dialog(update, context)
    elif data == "stats":
        await show_stats(update, context)
    else:
        await update.callback_query.answer()

# ===== Текстовий handler =====
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        return
    # Повідомлення від адміна у відповідь
    if update.effective_user.id == ADMIN_ID and ADMIN_ID in pending_replies:
        await admin_reply_message(update, context)
        return
    # Повідомлення користувача у підтримку
    if context.user_data.get("support_section"):
        await user_support_message(update, context)
        return
    # Пошук фільму
    await show_film(update, context, text)

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
