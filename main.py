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

# ===== Оновлення статистики =====
def update_user_stats(user):
    user_id = str(user.id)
    if user_id not in user_stats:
        user_stats[user_id] = {
            "username": user.username or "немає",
            "first_name": user.first_name or "немає",
            "raffle": False
        }
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(user_stats, f, indent=2, ensure_ascii=False)

# ===== Розіграш активний? =====
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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Відповісти", callback_data=f"reply_{user_id}")]
    ])

def winner_keyboard():
    return support_keyboard()

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
    user = update.effective_user
    update_user_stats(user)
    film = find_film_by_text(code_or_text)
    message = get_message(update)
    if not film:
        await message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(user.id == ADMIN_ID))
        return
    last_msg = context.user_data.get("last_film_message")
    text = f"🎬 {film['title']}\n\n{film['desc']}\n\n🔗 {film['link']}"
    if last_msg:
        try:
            await last_msg.edit_reply_markup(reply_markup=None)
        except:
            pass
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
        f"Привіт, {user.first_name}! 👋 Введи назву фільму або натисни кнопку нижче.",
        reply_markup=main_keyboard(user.id == ADMIN_ID)
    )

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
    if user_id not in user_stats:
        update_user_stats(query.from_user)
    user_stats[user_id]["raffle"] = True
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, indent=2, ensure_ascii=False)
    await query.message.edit_text("✅ Ви успішно взяли участь у розіграші MEGOGO!")

# ===== Статистика =====
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.callback_query.message
        total_users = len(user_stats)
        users_list = "\n".join([f"{u['first_name']} (@{u['username']})" for u in user_stats.values()])
        await message.reply_text(f"📊 Статистика бота:\nКількість користувачів: {total_users}\n\n{users_list}")
    except Exception as e:
        await update.callback_query.message.reply_text(f"❌ Помилка при завантаженні статистики: {e}")

# ===== Підтримка =====
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_stats(update.effective_user)
    await get_message(update).reply_text("Виберіть тему звернення:", reply_markup=support_keyboard())

async def support_topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["support_topic"] = query.data
    context.user_data["awaiting_support"] = True
    await query.message.reply_text("✉️ Введіть ваше повідомлення для підтримки:")

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        await query.message.reply_text("❌ Тільки адміністратор може відповідати.")
        return
    user_id = int(query.data.split("_")[1])
    context.user_data["awaiting_admin_reply"] = user_id
    await query.message.reply_text(f"✏️ Введіть відповідь для користувача ID: {user_id}")

# ===== Text handler =====
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_stats(user)
    username = user.username or "немає"
    text = update.message.text
    user_id = user.id

    # ===== Розсилка =====
    if context.user_data.get("awaiting_broadcast"):
        context.user_data["broadcast_message"] = update.message
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Так, надіслати", callback_data="broadcast_confirm")],
            [InlineKeyboardButton("❌ Скасувати", callback_data="broadcast_cancel")]
        ])
        await update.message.reply_text(
            "⚠️ Ви впевнені, що хочете надіслати це повідомлення всім користувачам?",
            reply_markup=keyboard
        )
        return

    if context.user_data.get("awaiting_support"):
        topic = context.user_data.get("support_topic", "support")
        support_requests.setdefault(str(user_id), []).append({"topic": topic, "message": text})
        with open(SUPPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(support_requests, f, indent=2, ensure_ascii=False)
        await update.message.reply_text("✅ Ваше повідомлення відправлено в підтримку!")
        await context.bot.send_message(chat_id=ADMIN_ID,
            text=f"✉️ Нове повідомлення у підтримку\n\n👤 Від: @{username}\n🆔 ID: {user_id}\n📂 Розділ: {topic}\n\n📨 Текст:\n{text}",
            reply_markup=admin_reply_keyboard(user_id))
        context.user_data["awaiting_support"] = False
        context.user_data["support_topic"] = None
        return

    awaiting_reply_id = context.user_data.get("awaiting_admin_reply")
    if awaiting_reply_id and user_id == ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=awaiting_reply_id, text=f"💬 Відповідь від підтримки:\n\n{text}")
            await update.message.reply_text("✅ Відповідь надіслано користувачу!")
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка при відправці: {e}")
        context.user_data["awaiting_admin_reply"] = None
        return

    await show_film(update, context, text)

# ===== Callback handler =====
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    update_user_stats(query.from_user)
    data = query.data
    if data == "random_film":
        await random_film(update, context)
    elif data == "raffle":
        await raffle(update, context)
    elif data == "raffle_join":
        await raffle_join_handler(update, context)
    elif data == "support":
        await support(update, context)
    elif data.startswith("support_"):
        await support_topic_handler(update, context)
    elif data.startswith("reply_"):
        await admin_reply_handler(update, context)
    elif data == "stats":
        if user_id == ADMIN_ID:
            await stats(update, context)
        else:
            await query.message.reply_text("❌ Тільки адміністратор може бачити статистику.")
    elif data == "raffle_participants":
        if user_id == ADMIN_ID:
            await raffle_participants_handler(update, context)
        else:
            await query.message.reply_text("❌ Тільки адміністратор може бачити учасників розіграшу.")
    elif data == "broadcast":
        await broadcast_start(update, context)
    elif data == "broadcast_confirm":
        await broadcast_confirm(update, context)
    elif data == "broadcast_cancel":
        await broadcast_cancel(update, context)

# ===== Broadcast confirm/cancel =====
async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    message = context.user_data.get("broadcast_message")
    if not message:
        await query.message.reply_text("❌ Немає повідомлення для розсилки.")
        return

    sent_count = 0
    failed_count = 0
    for uid in user_stats.keys():
        try:
            if message.text and not (message.photo or message.video):
                await context.bot.send_message(chat_id=int(uid), text=message.text)
            elif message.photo:
                await context.bot.send_photo(chat_id=int(uid), photo=message.photo[-1].file_id,
                                             caption=message.caption or message.text or "")
            elif message.video:
                await context.bot.send_video(chat_id=int(uid), video=message.video.file_id,
                                             caption=message.caption or message.text or "")
            sent_count += 1
        except Exception as e:
            print(f"❌ Не вдалося відправити {uid}: {e}")
            failed_count += 1

    await query.message.reply_text(f"📢 Розсилка завершена!\n✅ Успішно: {sent_count}\n❌ Помилок: {failed_count}")
    context.user_data["awaiting_broadcast"] = False
    context.user_data["broadcast_message"] = None


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_broadcast"] = False
    context.user_data["broadcast_message"] = None
    await query.message.reply_text("❌ Розсилка скасована.")


# ===== MAIN =====
async def main_async():
    app = ApplicationBuilder().token(TOKEN).build()
    await app.bot.delete_webhook(drop_pending_updates=True)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, text_handler))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(monthly_raffle, CronTrigger(day=1, hour=0, minute=0), args=[app])
    scheduler.start()
    await app.run_polling()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main_async())
