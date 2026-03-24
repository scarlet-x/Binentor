import os
import io
import time
import json
import logging
import re
import requests
import numpy as np
from PIL import Image

from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from binance.client import Client as BinanceClient
import google.generativeai as genai


# ---------------- CONFIG ----------------

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

WATCHLIST_FILE = "watchlist.json"
HISTORY_DIR = "history"
BINANCE_KEYS_FILE = "binance_keys.json"


# ---------------- AI ----------------

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel("gemma-3-27b-it")


# ---------------- CACHE ----------------

PRICE_CACHE = {}
CACHE_TIME = 5


# ---------------- FILE HELPERS ----------------

def read_md(filename):
    if not os.path.exists(filename):
        return ""
    with open(filename, "r", encoding="utf-8") as f:
        return f.read()


def update_memory(entry):
    if len(entry) < 10:
        return
    with open("memory.md", "a", encoding="utf-8") as f:
        f.write(f"\n- {entry}")


# ---------------- BINANCE KEY STORAGE ----------------

def load_binance_keys():
    if not os.path.exists(BINANCE_KEYS_FILE):
        return {}
    with open(BINANCE_KEYS_FILE) as f:
        return json.load(f)


def save_binance_keys(data):
    with open(BINANCE_KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user_binance_client(user_id):
    user_id = str(user_id)
    data = load_binance_keys()
    user = data.get(user_id)

    if not user:
        logger.warning(f"No Binance keys found for user {user_id}")
        return None

    try:
        return BinanceClient(
            user["api_key"],
            user["api_secret"],
            tld="com",
            requests_params={"timeout": 20}
        )
    except Exception as e:
        logger.error(f"Error creating Binance client: {e}")
        return None


# ---------------- HISTORY ----------------

def load_history(user_id):
    user_id = str(user_id)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = f"{HISTORY_DIR}/{user_id}.json"

    if not os.path.exists(path):
        return []

    with open(path) as f:
        return json.load(f)


def save_history(user_id, history):
    user_id = str(user_id)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = f"{HISTORY_DIR}/{user_id}.json"

    with open(path, "w") as f:
        json.dump(history[-20:], f)


# ---------------- MARKET ----------------

def get_price(symbol):
    now = time.time()

    if symbol in PRICE_CACHE:
        price, ts = PRICE_CACHE[symbol]
        if now - ts < CACHE_TIME:
            return price

    try:
        r = requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
            timeout=10
        )
        price = float(r.json()["price"])
        PRICE_CACHE[symbol] = (price, now)
        return price
    except Exception as e:
        logger.error(f"Price fetch error: {e}")
        return None


# ---------------- PORTFOLIO & TRADES ----------------

def get_portfolio(user_id):
    client = get_user_binance_client(user_id)

    if not client:
        return None

    try:
        account = client.get_account()
        balances = []

        for asset in account["balances"]:
            total = float(asset["free"]) + float(asset["locked"])

            if total > 0:
                balances.append((asset["asset"], total))

        return balances

    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        return None


def get_portfolio_summary(user_id):
    balances = get_portfolio(user_id)

    if balances is None:
        return "❌ Binance API error or not connected. Use /setbinance"

    if len(balances) == 0:
        return "⚠️ Binance connected, but no assets found."

    total_value = 0
    summary = []

    for asset, amount in balances:
        if asset == "USDT":
            value = amount
        else:
            price = get_price(asset + "USDT")
            if not price:
                continue
            value = amount * price

        total_value += value
        summary.append(f"{asset}: {round(amount,6)} (~${round(value,2)})")

    return f"""
💼 PORTFOLIO

Total: ${round(total_value,2)}

{chr(10).join(summary)}
"""

def get_recent_trades(user_id, symbol, limit=5):
    """Fetches recent trades for a specific symbol."""
    client = get_user_binance_client(user_id)
    
    if not client:
        return "❌ Binance API error or not connected. Use /setbinance"

    symbol = symbol.upper().strip()
    if not symbol.endswith("USDT") and not symbol.endswith("BTC"):
        symbol += "USDT" 

    try:
        trades = client.get_my_trades(symbol=symbol, limit=limit)
        
        if not trades:
            return f"No recent trades found for {symbol}."
            
        trade_strs = []
        for t in trades:
            side = "🟢 BUY" if t['isBuyer'] else "🔴 SELL"
            price = float(t['price'])
            qty = float(t['qty'])
            
            time_str = time.strftime('%Y-%m-%d %H:%M', time.gmtime(t['time'] / 1000.0))
            trade_strs.append(f"{time_str} | {side} {qty} @ ${price:,.2f}")
            
        return f"Recent {symbol} Trades:\n" + "\n".join(trade_strs)

    except Exception as e:
        logger.error(f"Trade history error for {symbol}: {e}")
        return f"⚠️ Could not fetch trades for {symbol}. (Check if the pair exists or if you have traded it)."


# ---------------- IMAGE ANALYSIS ----------------

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Reading chart data...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        img_bytes = await photo_file.download_as_bytearray()

        image = Image.open(io.BytesIO(img_bytes)).convert("L")
        img = np.array(image)

        brightness = img.mean()

        trend_bias = (
            "Bullish" if brightness > 160 else
            "Bearish" if brightness < 100 else
            "Sideways"
        )

        edges = np.mean(np.abs(np.diff(img, axis=1))) + np.mean(np.abs(np.diff(img, axis=0)))

        volatility = (
            "High" if edges > 40 else
            "Moderate" if edges > 20 else
            "Low"
        )

        personality = read_md("personality.md")

        prompt = f"""
{personality}

Trend: {trend_bias}
Volatility: {volatility}

Give short trading insight.
"""

        response = ai_model.generate_content(prompt)
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Chart analysis failed.")


# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Crypto Mentor Bot\n\n"
        "/setbinance <key> <secret>\n"
        "/portfolio\n"
        "/price BTC\n"
        "Send chart screenshot 📊"
    )


async def set_binance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if len(context.args) < 2:
        await update.message.reply_text("Usage:\n/setbinance <API_KEY> <API_SECRET>")
        return

    api_key = context.args[0]
    api_secret = context.args[1]

    client = BinanceClient(api_key, api_secret)

    try:
        client.get_account()
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid API keys:\n{e}")
        return

    data = load_binance_keys()
    data[user_id] = {
        "api_key": api_key,
        "api_secret": api_secret
    }

    save_binance_keys(data)

    await update.message.reply_text("✅ Binance connected successfully.")


async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = get_portfolio_summary(user_id)
    await update.message.reply_text(data)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return

    coin = context.args[0].upper()
    price = get_price(coin + "USDT")

    if not price:
        await update.message.reply_text("Token not found")
        return

    await update.message.reply_text(f"{coin}: ${price}")


# ---------------- AI CHAT ----------------

async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text

    history_list = load_history(user_id)
    history = "\n".join(history_list[-10:])

    portfolio_context = get_portfolio_summary(user_id)
    personality = read_md("personality.md")
    memory = read_md("memory.md")

    prompt = f"""
{personality}

Memory:
{memory}

Portfolio:
{portfolio_context}

History:
{history}

User: {text}

INSTRUCTIONS: 
1. Respond like a sharp crypto mentor. Max 5 sentences.
2. CRITICAL: If the user asks about their past trades, performance on a specific coin, or if you need their trade history for a specific token to answer the prompt, reply EXACTLY with:
FETCH_TRADES: <TICKER>
(Example: FETCH_TRADES: BTCUSDT). Do not include any other text in your response if you use this command.
"""

    await update.message.chat.send_action(constants.ChatAction.TYPING)

    try:
        # Pass 1: Initial LLM evaluation
        response = ai_model.generate_content(prompt)
        reply = response.text.strip()

        # Pass 2: Intercept the trigger, fetch data, and get final response
        if reply.startswith("FETCH_TRADES:"):
            symbol = reply.split("FETCH_TRADES:")[1].strip()
            
            # Fetch the actual trade history from Binance
            trade_data = get_recent_trades(user_id, symbol)
            
            # Inject the fetched data back to the LLM
            second_prompt = prompt + f"\n\n[SYSTEM UPDATE]: You requested trade history for {symbol}. Here is the data:\n{trade_data}\n\nNow, provide your final response to the user's original message based on this new data."
            
            second_response = ai_model.generate_content(second_prompt)
            reply = second_response.text.strip()

        # Save context
        history_list.extend([f"User: {text}", f"Bot: {reply}"])
        save_history(user_id, history_list)
        update_memory(f"User asked: {text}")

        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"AI Chat Error: {e}")
        await update.message.reply_text("❌ AI error. Please try again later.")


# ---------------- MAIN ----------------

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setbinance", set_binance))
    app.add_handler(CommandHandler("portfolio", portfolio))
    app.add_handler(CommandHandler("price", price))

    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat))

    logger.info("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
