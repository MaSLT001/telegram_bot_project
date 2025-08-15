import os
import json
import requests
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, CallbackQueryHandler, Filters

# ===== Завантаження фільмів =====
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

# ===== Реакції =====
REACTIONS_FILE = "reactions.json"
if os.path.exists(REACTIONS_FILE):
    with open(REACTIONS_FILE, "r", encoding="utf-8") as f:
        reactions = json.load(f)
else:
    reactions = {}  # {movie_code: {reaction_type: [user_id, ...]}}

# ===== Параметри =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
APP_URL = os.getenv("APP_URL")

if not TOKEN or not ADMIN_ID or not APP_URL:
    raise ValueError("Необхідно встановити BOT_TOKEN, ADMIN_ID та APP_URL у змінних середовища.")

ADMIN_ID = int(ADMIN_ID)

# ===== Бот і Flask =====
bot = Bot(token=TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot, None, workers=0)

support_mode_users = set()
reply_mode_admin = {}

# ===== Збереження =====
def save_stats():
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=4)

def save_reactions():
    with open(REACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(reactions, f, ensure_ascii=False, indent=4)

# ===== Клавіатури =====
def get_film_keyboard(share_text, movie_code):
    movie_reacts = reactions.get(movie_code, {})
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Поділитися", switch_inline_query=share_text),
            InlineKeyboardButton("💬 Підтримка", callback_data="support")
        ],
        [
            InlineKeyboardButton(f"👍 {len(movie_reacts.get('like', []))}", callback_data=f"react_{movie_code}_like"),
            InlineKeyboardButton(f"👎 {len(movie_reacts.get('dislike', []))}", callback_data=f"react_{movie_code}_dislike"),
            InlineKeyboardButton(f"😂 {len(movie_reacts.get('laugh', []))}", callback_data=f"react_{movie_code}_laugh"),
            InlineKeyboardButton(f"❤️ {len(movie_reacts.get('heart', []))}", callback_data=f"react_{movie_code}_heart"),
            InlineKeyboardButton(f"💩 {len(movie_reacts.get('poop', []))}", callback_data=f"react_{movie_code}_poop")
        ]
    ])

# ===== Команди =====
def start(update, context):
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.username or update.effective_user.full_name
    user_stats[user_id] = {"name": user_name, "visits": user_stats.get(user_id, {}).get("visits", 0) + 1}
    save_stats()
    update.message.reply_text("Привіт! Введи код фільму, щоб отримати інформацію.")

def find_movie(update, context):
    code = update.message.text.strip()
    if code in movies:
        film = movies[code]
        text = f"🎬 *{film['title']}*\n\n{film['desc']}\n\n🔗 {film['link']}"
        update.message.reply_text(text, parse_mode="Markdown",
                                  reply_markup=get_film_keyboard(share_text=text, movie_code=code))
    else:
        update.message.reply_text("❌ Фільм з таким кодом не знайдено.")

def handle_support_message(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    text = update.message.text

    # Відповідь адміна
    if user_id == ADMIN_ID and user_id in reply_mode_admin:
        target_user_id = reply_mode_admin[user_id]
        try:
            bot.send_message(chat_id=target_user_id, text=f"📩 Відповідь від підтримки:\n\n{text}")
            update.message.reply_text("✅ Повідомлення відправлено користувачу.")
        except:
            update.message.reply_text("⚠ Не вдалося відправити повідомлення користувачу.")
        return

    # Користувач у підтримку
    if user_id in support_mode_users:
        bot.send_message(chat_id=ADMIN_ID,
            text=f"📩 Нове повідомлення від користувача:\n👤 {username} (ID: {user_id})\n\n💬 {text}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏ Відповісти", callback_data=f"reply_{user_id}")]]))
        update.message.reply_text("✅ Ваше повідомлення відправлено в підтримку.")
        support_mode_users.remove(user_id)
    else:
        find_movie(update, context)

def support_callback(update, context):
    user_id = update.callback_query.from_user.id
    support_mode_users.add(user_id)
    update.callback_query.answer()
    update.callback_query.message.reply_text("✍ Напишіть своє повідомлення для підтримки, і я передам його.")

def reply_callback(update, context):
    query = update.callback_query
    data = query.data
    if data.startswith("reply_"):
        target_user_id = int(data.split("_")[1])
        reply_mode_admin[ADMIN_ID] = target_user_id
        query.answer()
        query.message.reply_text(f"✍ Ви увійшли в режим відповіді користувачу (ID: {target_user_id}).\n"
                                 f"Введіть повідомлення або напишіть /stopreply щоб вийти.")

def stop_reply(update, context):
    if update.effective_user.id == ADMIN_ID and ADMIN_ID in reply_mode_admin:
        del reply_mode_admin[ADMIN_ID]
        update.message.reply_text("🚪 Ви вийшли з режиму відповіді.")
    else:
        update.message.reply_text("⚠ Ви не в режимі відповіді.")

def reaction_callback(update, context):
    query = update.callback_query
    _, movie_code, reaction_type = query.data.split("_")
    user_id = query.from_user.id

    if movie_code not in reactions:
        reactions[movie_code] = {"like": [], "dislike": [], "laugh": [], "heart": [], "poop": []}

    # Видаляємо попередні голоси
    for key in reactions[movie_code]:
        if user_id in reactions[movie_code][key] and key != reaction_type:
            reactions[movie_code][key].remove(user_id)

    if user_id not in reactions[movie_code][reaction_type]:
        reactions[movie_code][reaction_type].append(user_id)
        save_reactions()

    share_text = f"🎬 {movies[movie_code]['title']} - Поділися!"
    query.message.edit_reply_markup(reply_markup=get_film_keyboard(share_text, movie_code))
    query.answer(f"Ви проголосували {reaction_type}")

# ===== Вебхук =====
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

# ===== Додавання хендлерів =====
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("stopreply", stop_reply))
dispatcher.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
dispatcher.add_handler(CallbackQueryHandler(reply_callback, pattern="^reply_"))
dispatcher.add_handler(CallbackQueryHandler(reaction_callback, pattern="^react_"))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_support_message))

# ===== Автоматична перевірка вебхука =====
def set_or_check_webhook():
    WEBHOOK_URL = f"{APP_URL}/{TOKEN}"
    try:
        info = requests.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo").json()
        current_url = info.get("result", {}).get("url", "")
        if current_url != WEBHOOK_URL:
            resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}")
            if resp.status_code == 200:
                print("✅ Вебхук успішно встановлений або оновлений!")
            else:
                print(f"⚠ Помилка при встановленні вебхука: {resp.text}")
        else:
            print("ℹ Вебхук вже встановлений і актуальний.")
    except Exception as e:
        print(f"⚠ Помилка при перевірці вебхука: {e}")

if __name__ == "__main__":
    print("BOT_TOKEN set:", TOKEN is not None)
    print("ADMIN_ID:", ADMIN_ID)
    print("APP_URL set:", APP_URL)
    set_or_check_webhook()
    print("Бот запущений через вебхук...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
