from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)

from binentor.config.settings import TELEGRAM_TOKEN
from binentor.bot.handlers import start, handle_message


def start_bot():
    """
    Initializes and starts the Telegram bot.
    """
    # Build the application with your token
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Register the /start command handler
    app.add_handler(CommandHandler("start", start))

    # Register the handler for all other text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Binentor bot running...")

    # Start the bot's polling loop
    app.run_polling()


if __name__ == "__main__":
    start_bot()
