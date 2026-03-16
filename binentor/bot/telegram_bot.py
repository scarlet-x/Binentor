from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)

from binentor.config.settings import TELEGRAM_TOKEN
from binentor.bot.handlers import start, handle_message


def start_bot():

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Binentor bot running...")

    app.run_polling()
