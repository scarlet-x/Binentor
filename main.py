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

    data = load_binance_keys()
    user = data.get(str(user_id))

    if not user:
        return None

    try:
        return BinanceClient(
            user["api_key"],
            user["api_secret"],
            tld="com",
            requests_params={"timeout": 20}
        )
    except:
        return None


# ---------------- HISTORY ----------------

def load_history(user_id):

    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = f"{HISTORY_DIR}/{user_id}.json"

    if not os.path.exists(path):
        return []

    with open(path) as f:
        return json.load(f)


def save_history(user_id, history):

    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = f"{HISTORY_DIR}/{user_id}.json"

    with open(path, "w") as f:
        json.dump(history[-20:], f)


# ---------------- WATCHLIST ----------------

def load_watchlist():

    if not os.path.exists(WATCHLIST_FILE):
        return {}

    with open(WATCHLIST_FILE) as f:
        return json.load(f)


def save_watchlist(data):

    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------- MARKET ----------------

def get_price(symbol):

    now = time.time()

    if symbol in PRICE_CACHE:
        price, ts = PRICE_CACHE[symbol]
        if now - ts < CACHE_TIME:
            return price

    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
        price = float(r.json()["price"])
        PRICE_CACHE[symbol] = (price, now)
        return price
    except:
        return None


# ---------------- PORTFOLIO ----------------

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
        logger.error(e)
        return None


def get_portfolio_summary(user_id):

    balances = get_portfolio(user_id)

    if not balances:
        return "⚠️ No Binance account connected. Use /setbinance"

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


# ---------------- IMAGE ANALYSIS ----------------

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("📊 Reading chart data...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        img_bytes = await photo_file.download_as_bytearray()

        image = Image.open(io.BytesIO(img_bytes)).convert("L")

        width, height = image.size
        img = np.array(image)

        brightness = img.mean()

        if brightness > 160:
            trend_bias = "Bullish"
        elif brightness < 100:
            trend_bias = "Bearish"
        else:
            trend_bias = "Sideways"

        gx = np.abs(np.diff(img, axis=1))
        gy = np.abs(np.diff(img, axis=0))
        edges = np.mean(gx) + np.mean(gy)

        if edges > 40:
            volatility = "High"
        elif edges > 20:
            volatility = "Moderate"
        else:
            volatility = "Low"

        horizontal = np.mean(img, axis=1)

        support = list(np.argsort(horizontal)[:3])
        resistance = list(np.argsort(horizontal)[-3:])

        mid = height // 2
        if np.mean(img[mid-20:mid+20]) > brightness:
            price_zone = "Upper zone"
        else:
            price_zone = "Lower zone"

        personality = read_md("personality.md")

        context_text = f"""
{personality}

Chart Data:

Trend: {trend_bias}
Volatility: {volatility}
Price Zone: {price_zone}

Support (px): {support}
Resistance (px): {resistance}

Give a short trading insight.
"""

        response = ai_model.generate_content(context_text)

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
        await update.message.reply_text(
            "Usage:\n/setbinance <API_KEY> <API_SECRET>"
        )
        return

    api_key = context.args[0]
    api_secret = context.args[1]

    data = load_binance_keys()
    data[user_id] = {
        "api_key": api_key,
        "api_secret": api_secret
    }

    save_binance_keys(data)

    await update.message.reply_text("✅ Binance connected.")


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

    await update.message.reply_text(f"{coin} price: ${price}")


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

Long-term Memory:
{memory}

Portfolio:
{portfolio_context}

Recent Conversation:
{history}

User: {text}

Respond like a sharp crypto mentor.
Be concise, confident, practical.
Max 5 sentences.
"""

    await update.message.chat.send_action(constants.ChatAction.TYPING)

    try:
        response = ai_model.generate_content(prompt)
        reply = response.text

        history_list.extend([f"User: {text}", f"Bot: {reply}"])
        save_history(user_id, history_list)

        update_memory(f"User asked: {text}")

        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(e)
        await update.message.reply_text("AI error.")


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
