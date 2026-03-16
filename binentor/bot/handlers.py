import re
from telegram import Update
from telegram.ext import ContextTypes

from binentor.openclaw.agents.runner import run_agent
from binentor.openclaw.memory.store import set_user_keys, get_user_keys


MAX_RESPONSE_LENGTH = 900


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 Welcome to **Binentor**.\n\n"
        "Before we start, connect your Binance API.\n\n"
        "Send it like this:\n\n"
        "API: your_api_key\n"
        "SECRET: your_secret_key"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = str(update.effective_user.id)
    message = update.message.text.strip()

    # Detect API credentials
    api_match = re.search(r"API:\s*(.+)", message, re.IGNORECASE)
    secret_match = re.search(r"SECRET:\s*(.+)", message, re.IGNORECASE)

    if api_match and secret_match:

        api_key = api_match.group(1).strip()
        secret_key = secret_match.group(1).strip()

        set_user_keys(user_id, api_key, secret_key)

        await update.message.reply_text(
            "✅ Binance API connected.\n\n"
            "Now you can ask things like:\n"
            "• Should I buy BTC now?\n"
            "• Analyze my trades\n"
            "• Explain RSI"
        )

        return

    # Check if user already connected API
    keys = get_user_keys(user_id)

    if not keys:

        await update.message.reply_text(
            "⚠️ You need to connect your Binance API first.\n\n"
            "Send:\n"
            "API: your_api_key\n"
            "SECRET: your_secret_key"
        )

        return

    # Send message to agent
    response = await run_agent(user_id, message)

    if not response:
        response = "Hmm, I couldn't analyze that. Try asking in another way."

    # Hard limit response length
    if len(response) > MAX_RESPONSE_LENGTH:
        response = response[:MAX_RESPONSE_LENGTH] + "..."

    await update.message.reply_text(response)
