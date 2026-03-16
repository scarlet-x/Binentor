import re
from telegram import Update
from telegram.ext import ContextTypes

from binentor.openclaw.agents.runner import run_agent
from binentor.openclaw.memory.store import set_user_keys, get_user_keys


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 Welcome to **Binentor**.\n\n"
        "Before we start, please send your Binance credentials.\n\n"
        "Format:\n"
        "API: your_api_key\n"
        "SECRET: your_secret_key"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = str(update.effective_user.id)
    message = update.message.text

    api_match = re.search(r"API:\s*(.+)", message)
    secret_match = re.search(r"SECRET:\s*(.+)", message)

    if api_match and secret_match:

        api_key = api_match.group(1).strip()
        secret_key = secret_match.group(1).strip()

        set_user_keys(user_id, api_key, secret_key)

        await update.message.reply_text(
            "✅ Binance API connected successfully.\n\n"
            "You can now ask trading questions."
        )

        return

    keys = get_user_keys(user_id)

    if not keys:

        await update.message.reply_text(
            "⚠️ Please connect your Binance API first.\n\n"
            "Send:\nAPI: your_api_key\nSECRET: your_secret_key"
        )

        return

    response = await run_agent(user_id, message)

    await update.message.reply_text(response)
