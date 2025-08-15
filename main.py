import json
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from dotenv import load_dotenv

# ===== Завантажуємо токен і ID з .env =====
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ===== Завантаження фільмів =====
try:
    with open("movies.json", "r", encoding="utf-8") as f:
        movies = json.load(f)
except FileNotFoundError:
    movies = {}

# ===== Завантаження реакцій =====
try:
    with open("reactions.json", "r", encoding="utf-8") as f:
        reactions = json.load(f)
except FileNotFoundError:
    reactions = {}

# ===== Завантаження користувачів =====
try:
    with open("users.json", "r", encoding="utf-8") as f:
        user_stats = json.load(f)
except FileNotFoundError:
    user_stats = {}

# ===== Функції збереження =====
def save_reactions():
    with open("reactions.json", "w", encoding="utf-8") as f:
        json.dump(reactions, f, ensure_ascii=False, indent=2)

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=2)

# ===== Генерація клавіатури фільму =====
def get_film_keyboard(share_text, movie_code):
    movie_reacts = reactions.get(movie_code, {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []})
    keyboard = [
        [
            InlineKeyboardButton(f"👍 {len(movie_reacts['like'])}", callback_data=f"react_{movie_code}_like"),
            InlineKeyboardButton(f"👎 {len(movie_reacts['dislike'])}", callback_data=f"react_{movie_code}_dislike"),
        ],
        [
            InlineKeyboardButton(f"😂 {len(movie_reacts['laugh'])}", callback_data=f"react_{movie_code}_laugh"),
            InlineKeyboardButton(f"❤️ {len(movie_reacts['heart'])}", callback_data=f"react_{movie_code}_heart"),
            InlineKeyboardButton(f"💩 {len(movie_reacts['poop'])}", callback_data=f"react_{movie_code}_poop"),
        ],
        [InlineKeyboardButton("📤 Поділитися", switch_inline_query=share_text)],
        [InlineKeyboardButton("💬 Підтримка", callback_data="support")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.full_name

    if str(user_id) not in user_stats:
        user_stats[str(user_id)] = {"name": name, "visits": 1}
    else:
        user_stats[str(user_id)]["visits"] += 1
    save_users()

    if movies:
        first_movie_code = next(iter(movies))
        await update.message.reply_text(
            "🎬 Привіт! Ось перший фільм:",
            reply_markup=get_film_keyboard("Поділися цим фільмом!", first_movie_code)
        )
    else:
        await update.message.reply_text("❌ Немає доступних фільмів.")

async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total_users = len(user_stats)
    total_visits = sum(u.get("visits", 0) for u in user_stats.values())
    text = f"👥 Користувачів: {total_users}\n✉ Повідомлень: {total_visits}\n\n"
    text += "\n".join(f"{u['name']} (ID: {uid})" for uid, u in user_stats.items())
    await update.message.reply_text(text)

async def send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Використання: /sendall <текст>")
        return
    msg = " ".join(context.args)
    for uid in user_stats.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
        except:
            pass
    await update.message.reply_text("✅ Розсилка завершена")

# ===== Реакції =====
async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, movie_code, reaction_type = query.data.split("_")
    user_id = query.from_user.id

    if movie_code not in reactions:
        reactions[movie_code] = {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []}

    for key in reactions[movie_code]:
        if user_id in reactions[movie_code][key] and key != reaction_type:
            reactions[movie_code][key].remove(user_id)

    if user_id in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].remove(user_id)
    else:
        reactions[movie_code][reaction_type].append(user_id)

    save_reactions()

    movie_data = movies.get(movie_code, {"title": "Невідомо", "desc": "", "link": ""})
    share_text = f"🎬 {movie_data['title']}\n\n{movie_data['desc']}\n\n{movie_data['link']}"
    await query.message.edit_reply_markup(reply_markup=get_film_keyboard(share_text, movie_code))
    await query.answer("✅ Реакція збережена!")

# ===== Запуск бота =====
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot = Bot(TOKEN)
    try:
        bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook видалено, старі оновлення очищені.")
    except Exception as e:
        print(f"⚠ Не вдалося видалити webhook: {e}")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CallbackQueryHandler(reaction_callback, pattern="^react_"))

    print("🚀 Бот запущений...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
