import os
import json
import random
from github import Github
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from deep_translator import GoogleTranslator
from difflib import get_close_matches
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import nest_asyncio

# ===== FIX для Render/Jupyter =====
nest_asyncio.apply()

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
        [InlineKeyboardButton("🎁 Розіграш", callback_data="giveaway")],
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all")
        ])
        buttons.append([
            InlineKeyboardButton("🎁 Учасники розіграшу", callback_data="giveaway_participants")
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
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    film = movies.get(code) or find_film_by_text(code)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id == ADMIN_ID))
        return

    # Прибираємо кнопки з попереднього повідомлення
    last_msg_id = context.user_data.get('last_film_message')
    if last_msg_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=message.chat_id,
                message_id=last_msg_id,
                reply_markup=None
            )
        except:
            pass

    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    sent_message = await message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text, update.effective_user.id == ADMIN_ID))
    context.user_data['last_film_message'] = sent_message.message_id

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

# ===== Розсилка всім =====
async def send_all_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    await update.callback_query.edit_message_text("✉️ Введіть повідомлення для всіх користувачів:")
    context.user_data['send_all'] = True

async def handle_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('send_all') and 'pending_text' not in context.user_data:
        context.user_data['pending_text'] = update.message.text
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Відправити", callback_data="confirm_send_all"),
                InlineKeyboardButton("❌ Скасувати", callback_data="cancel_send_all")
            ]
        ])
        await update.message.reply_text(f"⚠️ Ви впевнені, що хочете надіслати наступне повідомлення всім користувачам?\n\n{update.message.text}", reply_markup=keyboard)
        context.user_data['send_all'] = False

async def confirm_send_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = context.user_data.pop('pending_text', None)
    if text:
        for uid in user_stats:
            try:
                await context.bot.send_message(int(uid), text)
            except:
                pass
        await update.callback_query.edit_message_text("✅ Повідомлення надіслано всім користувачам", reply_markup=main_keyboard(True))
    else:
        await update.callback_query.edit_message_text("❌ Помилка: немає тексту для відправки", reply_markup=main_keyboard(True))

async def cancel_send_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("❌ Розсилка скасована")
    context.user_data.pop('pending_text', None)
    await update.callback_query.edit_message_text("❌ Розсилка скасована", reply_markup=main_keyboard(True))

# ===== Підтримка =====
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Звернення", callback_data="support_request")],
        [InlineKeyboardButton("2️⃣ Співпраця", callback_data="support_collab")],
        [InlineKeyboardButton("3️⃣ Повідомити про перемогу в розіграші", callback_data="support_giveaway")],
    ])
    await update.callback_query.message.reply_text("✉️ Виберіть варіант звернення:", reply_markup=keyboard)

# ===== Розіграш =====
GIVEAWAY_KEY = "giveaway"

async def join_giveaway_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    user_stats[uid][GIVEAWAY_KEY] = True
    save_stats()
    await update.callback_query.answer("🎁 Ви приєдналися до розіграшу!", show_alert=True)
    await update.callback_query.edit_message_text("✅ Ви успішно взяли участь у розіграші!")

async def giveaway_participants_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    participants = [u for u, v in user_stats.items() if v.get(GIVEAWAY_KEY)]
    text = "🎁 Учасники розіграшу:\n\n" + "\n".join([f"{user_stats[u]['first_name']} (@{user_stats[u].get('username','')})" for u in participants])
    await update.callback_query.edit_message_text(text, reply_markup=main_keyboard(True))

async def run_giveaway(bot):
    participants = [uid for uid, data in user_stats.items() if data.get(GIVEAWAY_KEY)]
    if not participants:
        print("❌ Немає учасників розіграшу")
        return
    winner_id = random.choice(participants)
    winner_data = user_stats[winner_id]

    # Повідомлення переможцю
    try:
        await bot.send_message(int(winner_id), f"🎉 Вітаємо {winner_data['first_name']}! Ви виграли місячну максимальну підписку на Megogo! Напишіть в підтримку для отримання призу.")
    except:
        pass

    # Повідомлення адміну
    try:
        await bot.send_message(ADMIN_ID, f"🎉 Користувач {winner_data['first_name']} (@{winner_data.get('username','')}) виграв розіграш!")
    except:
        pass

    # Скидаємо участь для нового місяця
    for uid in user_stats:
        user_stats[uid][GIVEAWAY_KEY] = False
    save_stats()

    # Повідомлення всім, хто ще не приєднався до нового розіграшу
    for uid, data in user_stats.items():
        if not data.get(GIVEAWAY_KEY):
            try:
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Взяти участь", callback_data="giveaway")]])
                await bot.send_message(int(uid), "🎁 Новий розіграш почався! Натисніть кнопку, щоб взяти участь.", reply_markup=keyboard)
            except:
                pass

async def giveaway_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await join_giveaway_callback(update, context)

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": user.username, "first_name": user.first_name, GIVEAWAY_KEY: False}
        save_stats()

    keyboard = main_keyboard(user.id == ADMIN_ID)
    if not user_stats[uid].get(GIVEAWAY_KEY):
        giveaway_button = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Взяти участь у розіграші", callback_data="giveaway")]])
        await update.message.reply_text(
            f"Привіт, {user.first_name}! 👋 Введи назву фільму або його код, або натисни кнопку нижче 😉",
            reply_markup=giveaway_button
        )

    await update.message.reply_text(
        f"Привіт, {user.first_name}! 👋 Введи назву фільму або його код, або натисни кнопку нижче 😉",
        reply_markup=keyboard
    )

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    save_stats()
    await show_film(update, context, code)

# ===== Main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Команди та хендлери
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code))
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(send_all_message, pattern="^send_all$"))
    app.add_handler(CallbackQueryHandler(confirm_send_all_callback, pattern="^confirm_send_all$"))
    app.add_handler(CallbackQueryHandler(cancel_send_all_callback, pattern="^cancel_send_all$"))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(giveaway_callback, pattern="^giveaway$"))
    app.add_handler(CallbackQueryHandler(giveaway_participants_callback, pattern="^giveaway_participants$"))

    # Планувальник для щомісячного розіграшу
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_giveaway, "cron", day=1, hour=12, minute=0, args=[app.bot])
    scheduler.start()

    print("✅ Бот запущений")
    app.run_polling()  # запускає event loop самостійно

if __name__ == "__main__":
    main()

