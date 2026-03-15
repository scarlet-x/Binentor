from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from binentor.config.settings import TELEGRAM_TOKEN
from binentor.openclaw.agents.runner import run_agent


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Binentor.\n"
        "Your Binance trading mentor.\n\n"
        "Ask anything about trading."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = str(update.effective_user.id)
    message = update.message.text

    response = await run_agent(user_id, message)

    await update.message.reply_text(response)


def start_bot():

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running...")
    app.run_polling()
