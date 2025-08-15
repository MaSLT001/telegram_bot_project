import os
import json
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler, CallbackContext

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)

# Завантаження фільмів та реакцій
with open("movies.json", "r", encoding="utf-8") as f:
    movies = json.load(f)

if os.path.exists("reactions.json"):
    with open("reactions.json", "r", encoding="utf-8") as f:
        reactions_data = json.load(f)
else:
    reactions_data = {}  # structure: {movie_id: {"👍":0,"👎":0,"❤️":0,"😂":0,"💩":0}}

# Кнопка Рандомного фільму
def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("🎬 Рандомний фільм", callback_data="random_movie")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Привіт! Обери фільм:", reply_markup=reply_markup)

def send_random_movie(update: Update, context: CallbackContext):
    import random
    movie = random.choice(movies)
    movie_id = str(movie["id"])

    # Ініціалізація реакцій, якщо немає
    if movie_id not in reactions_data:
        reactions_data[movie_id] = {"👍":0,"👎":0,"❤️":0,"😂":0,"💩":0}

    keyboard = [
        [
            InlineKeyboardButton("👍", callback_data=f"react_{movie_id}_👍"),
            InlineKeyboardButton("👎", callback_data=f"react_{movie_id}_👎"),
            InlineKeyboardButton("❤️", callback_data=f"react_{movie_id}_❤️"),
            InlineKeyboardButton("😂", callback_data=f"react_{movie_id}_😂"),
            InlineKeyboardButton("💩", callback_data=f"react_{movie_id}_💩")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.callback_query.message.reply_text(f"{movie['title']}", reply_markup=reply_markup)
    update.callback_query.answer()

def handle_reaction(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data  # наприклад: react_1_👍
    _, movie_id, emoji = data.split("_")
    reactions_data.setdefault(movie_id, {"👍":0,"👎":0,"❤️":0,"😂":0,"💩":0})
    reactions_data[movie_id][emoji] += 1

    # Зберігаємо у reactions.json
    with open("reactions.json", "w", encoding="utf-8") as f:
        json.dump(reactions_data, f, ensure_ascii=False, indent=4)

    query.answer(f"Ваша реакція {emoji} зафіксована!")

# Диспетчер для Flask
dispatcher = Dispatcher(bot, None, workers=0)
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CallbackQueryHandler(send_random_movie, pattern="^random_movie$"))
dispatcher.add_handler(CallbackQueryHandler(handle_reaction, pattern="^react_"))

# Flask route для webhook
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"

if __name__ == "__main__":
    # Встановлюємо webhook на URL Render
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # наприклад: https://yourapp.onrender.com/<BOT_TOKEN>
    bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook встановлено на {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
