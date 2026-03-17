import re
from telegram import Update
from telegram.ext import ContextTypes

from binentor.openclaw.agents.runner import run_agent
from binentor.openclaw.memory.store import set_user_keys, get_user_keys

# Limit the response to avoid hitting Telegram's message limits
MAX_RESPONSE_LENGTH = 900

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Initial greeting and instruction to connect Binance API.
    """
    await update.message.reply_text(
        "👋 Welcome to **Binentor**.\n\n"
        "I am your trading mentor. To give you personalized guidance based on your "
        "actual holdings and orders, I need access to your Binance account.\n\n"
        "Please send your credentials in this format:\n\n"
        "API: your_api_key\n"
        "SECRET: your_secret_key\n\n"
        "*Note: Use a Read-Only API key for maximum security.*"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all incoming text messages. Detects API keys or processes trading queries.
    """
    user_id = str(update.effective_user.id)
    message = update.message.text.strip()

    # 1. Check if the user is trying to connect their Binance API
    api_match = re.search(r"API:\s*(.+)", message, re.IGNORECASE)
    secret_match = re.search(r"SECRET:\s*(.+)", message, re.IGNORECASE)

    if api_match and secret_match:
        api_key = api_match.group(1).strip()
        secret_key = secret_match.group(1).strip()

        # Save keys to the store
        set_user_keys(user_id, api_key, secret_key)

        await update.message.reply_text(
            "✅ **Binance API connected successfully.**\n\n"
            "Now I can analyze your account to give you better advice. Try asking:\n"
            "• 'What does my current portfolio look like?'\n"
            "• 'Check my open orders.'\n"
            "• 'Based on my balance, is it a good time to buy BTC?'"
        )
        return

    # 2. Check if the user has already connected their API
    keys = get_user_keys(user_id)

    if not keys:
        await update.message.reply_text(
            "⚠️ **Binance API not found.**\n\n"
            "I need to see your account data to provide guidance. Please send your keys:\n\n"
            "API: your_api_key\n"
            "SECRET: your_secret_key"
        )
        return

    # 3. If connected, pass the message to the agent runner
    # The runner will handle fetching the live Binance data and generating a response
    response = await run_agent(user_id, message)

    if not response:
        response = "I couldn't process that. Could you try rephrasing your question?"

    # Ensure the response stays within Telegram's constraints
    if len(response) > MAX_RESPONSE_LENGTH:
        response = response[:MAX_RESPONSE_LENGTH].rstrip() + "..."

    await update.message.reply_text(response)
