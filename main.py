
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

MOVIES_FILE = "movies.json"
REACTIONS_FILE = "reactions.json"

REACTIONS = ["👍", "👎", "❤️", "😂", "💩"]

def load_reactions():
    try:
        with open(REACTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_reactions(data):
    with open(REACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

reactions_data = load_reactions()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Обери фільм та оцінюй його.")

async def show_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(MOVIES_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)
    movie = movies[0]  # поки перший фільм
    buttons = [[InlineKeyboardButton(r, callback_data=f"{movie['id']}|{r}") for r in REACTIONS]]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(f"Фільм: {movie['title']}", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    movie_id, reaction = query.data.split("|")
    
    if movie_id not in reactions_data:
        reactions_data[movie_id] = {r: 0 for r in REACTIONS}
    reactions_data[movie_id][reaction] += 1
    save_reactions(reactions_data)
    
    await query.edit_message_text(f"Оцінки:\n" +
        "\n".join([f"{r}: {reactions_data[movie_id][r]}" for r in REACTIONS])
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("movie", show_movie))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()
