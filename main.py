from telegram import Bot

# ===== Запуск бота =====
if __name__ == "__main__":
    # Створюємо об'єкт бота для видалення webhook
    bot = Bot(token=TOKEN)
    try:
        bot.delete_webhook()
        print("Webhook видалено, можна запускати polling.")
    except Exception as e:
        print(f"Не вдалося видалити webhook: {e}")

    # Створюємо та запускаємо Application
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendall", send_all))
    app.add_handler(CommandHandler("stopreply", stop_reply))
    app.add_handler(CommandHandler("stats", send_stats))
    app.add_handler(CallbackQueryHandler(support_callback, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(reply_callback, pattern="^reply_"))
    app.add_handler(CallbackQueryHandler(reaction_callback, pattern="^react_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message))

    print("Бот запущений...")
    app.run_polling()
