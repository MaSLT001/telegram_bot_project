import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ===== Змінні оточення =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
if not TOKEN or not ADMIN_ID:
    raise ValueError("Встановіть BOT_TOKEN та ADMIN_ID у environment variables")

# ===== Завантаження даних =====
def load_json(file, default={}):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

movies = load_json("movies.json")
user_stats = load_json("stats.json")
reactions = load_json("reactions.json")

# ===== Збереження =====
def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ===== Статистика користувачів =====
def update_user_stats(user_id, name):
    user_stats[user_id] = {
        "name": name,
        "visits": user_stats.get(user_id, {}).get("visits", 0) + 1
    }
    save_json("stats.json", user_stats)

# ===== Клавіатури =====
def get_film_keyboard(share_text, movie_code):
    movie_reacts = reactions.get(movie_code, {"like":[],"dislike":[],"laugh":[],"heart":[],"poop":[]})
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Поділитися", switch_inline_query=share_text),
         InlineKeyboardButton("💬 Підтримка", callback_data="support")],
        [InlineKeyboardButton(f"👍 {len(movie_reacts.get('like', []))}", callback_data=f"react_{movie_code}_like"),
         InlineKeyboardButton(f"👎 {len(movie_reacts.get('dislike', []))}", callback_data=f"react_{movie_code}_dislike"),
         InlineKeyboardButton(f"😂 {len(movie_reacts.get('laugh', []))}", callback_data=f"react_{movie_code}_laugh"),
         InlineKeyboardButton(f"❤️ {len(movie_reacts.get('heart', []))}", callback_data=f"react_{movie_code}_heart"),
         InlineKeyboardButton(f"💩 {len(movie_reacts.get('poop', []))}", callback_data=f"react_{movie_code}_poop")]
    ])

def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомний фільм", callback_data="random_film")]
    ])

# ===== Команди =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    name = update.effective_user.username or update.effective_user.full_name
    update_user_stats(user_id, name)
    await update.message.reply_text("Привіт! Вибери опцію:", reply_markup=get_start_keyboard())

# ===== Рандомний фільм =====
async def random_film_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    code = random.choice(list(movies.keys()))
    film = movies[code]
    text = f"🎬 {film['title']}\n\n{film['desc']}\n\n🔗 {film['link']}"
    await query.message.reply_text(text, reply_markup=get_film_keyboard(text, code))
    await query.answer()

# ===== Реакції =====
async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, movie_code, reaction_type = query.data.split("_")
    user_id = query.from_user.id
    if movie_code not in reactions:
        reactions[movie_code] = {"like":[],"dislike":[],"laugh":[],"heart":[],"poop":[]}
    # Видаляємо інші реакції
    for key in reactions[movie_code]:
        if user_id in reactions[movie_code][key] and key != reaction_type:
            reactions[movie_code][key].remove(user_id)
    if user_id not in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].append(user_id)
    save_json("reactions.json", reactions)
    # Оновлюємо кнопки
    film = movies[movie_code]
    share_text = f"🎬 {film['title']} - Поділися!"
    await query.message.edit_reply_markup(reply_markup=get_film_keyboard(share_text, movie_code))
    await query.answer(f"Ви проголосували {reaction_type}")

# ===== Статистика =====
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас немає прав для цієї команди.")
        return
    text = "📊 Статистика користувачів:\n\n"
    for uid, info in user_stats.items():
        text += f"👤 {info['name']} (ID: {uid}) - Відвідувань: {info['visits']}\n"
    await update.message.reply_text(text)

# ===== Повідомлення підтримки =====
support_mode_users = set()
reply_mode_admin = {}

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    text = update.message.text
    # Якщо адмін у режимі відповіді
    if user_id == ADMIN_ID and user_id in reply_mode_admin:
        target_user_id = reply_mode_admin[user_id]
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"📩 Відповідь від підтримки:\n{text}")
            await update.message.reply_text("✅ Відправлено користувачу")
        except:
            await update.message.reply_text("⚠ Не вдалося відправити")
        return
    if user_id in support_mode_users:
        await context.bot.send_message(chat_id=ADMIN_ID,
                                       text=f"📩 Нове повідомлення від користувача:\n👤 {username} (ID:{user_id})\n{text}")
        await update.message.reply_text("✅ Повідомлення відправлено в підтримку")
        support_mode_users.remove(user_id)

# ===== Хендлери =====
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_support_message(update, context)

# ===== Запуск бота =====
bot = Bot(TOKEN)
bot.delete_webhook()  # щоб уникнути Conflict

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CallbackQueryHandler(random_film_callback, pattern="random_film"))
app.add_handler(CallbackQueryHandler(reaction_callback, pattern="react_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

print("Бот запущений...")
app.run_polling()
