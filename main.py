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

# ===== ENV перемінні =====
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
        [InlineKeyboardButton("✉️ Підтримка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all")
        ])
    return InlineKeyboardMarkup(buttons)

def film_keyboard(text, is_admin=False):
    buttons = [
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support"),
            InlineKeyboardButton("📋 Меню", callback_data="menu")
        ],
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("📢 Відправити всім", callback_data="send_all")
        ])
    return InlineKeyboardMarkup(buttons)

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
    matches = get_close_matches(translated, titles, n=1, cutoff=0.6)
    if matches:
        return next(f for f in movies.values() if f['title'] == matches[0])
    return None

# ===== Показ фільму =====
async def show_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    film = movies.get(code)
    if not film:
        film = find_film_by_text(code)
    if not film:
        await update.message.reply_text("❌ Фільм не знайдено", reply_markup=main_keyboard(update.effective_user.id==ADMIN_ID))
        return
    text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=film_keyboard(text, update.effective_user.id==ADMIN_ID))

async def random_film(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not movies:
        await update.callback_query.answer("❌ Список фільмів порожній.")
        return
    code = random.choice(list(movies.keys()))
    await show_film(update.callback_query, context, code)
    await update.callback_query.answer()

# ===== Меню =====
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_ID
    await update.callback_query.edit_message_text(
        "📋 Головне меню",
        reply_markup=main_keyboard(is_admin)
    )

# ===== Статистика =====
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    total_users = len(user_stats)
    await update.callback_query.edit_message_text(f"📊 Користувачів: {total_users}", reply_markup=main_keyboard(True))

# ===== Відправка всім =====
async def send_all_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("❌ Немає доступу", show_alert=True)
        return
    await update.callback_query.edit_message_text("✉️ Введіть повідомлення для всіх користувачів:")
    context.user_data['send_all'] = True

async def handle_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('send_all'):
        text = update.message.text
        for uid in user_stats:
            try:
                await context.bot.send_message(int(uid), text)
            except:
                pass
        context.user_data['send_all'] = False
        await update.message.reply_text("✅ Повідомлення надіслано всім користувачам", reply_markup=main_keyboard(True))

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": user.username, "first_name": user.first_name}
        save_stats()
    await update.message.reply_text(
        f"Привіт, {user.first_name}!👋 Введи код фільму або натисни кнопку нижче щоб ми тобі запропонували фільм😉",
        reply_markup=main_keyboard(uid==str(ADMIN_ID))
    )

async def movie_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    uid = str(update.effective_user.id)
    if uid not in user_stats:
        user_stats[uid] = {"username": update.effective_user.username, "first_name": update.effective_user.first_name}
    save_stats()
    # Перевірка, чи це повідомлення для розсилки
    if context.user_data.get('send_all'):
        await handle_send_all(update, context)
        return
    await show_film(update, context, code)

# ===== Main =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie_by_code))
    app.add_handler(CallbackQueryHandler(random_film, pattern="^random_film$"))
    app.add_handler(CallbackQueryHandler(show_menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(send_all_message, pattern="^send_all$"))
    print("✅ Бот запущений")
    app.run_polling()

if __name__ == "__main__":
    main()
