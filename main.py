import os
import io
import re
import logging
import sqlite3
import contextvars
import requests
import cv2
import numpy as np
import pytesseract

from PIL import Image

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

from binance.client import Client as BinanceClient
import google.generativeai as genai

# --- CONFIG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- MODEL WRAPPER ---
class AIModel:
    def __init__(self, model_name):
        genai.configure(api_key=GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(model_name)

    async def generate(self, content):
        return await self.model.generate_content_async(content)

    def start_chat(self, history):
        return self.model.start_chat(history=history)


chat_model = AIModel("gemma-3-27b-it")

current_user_id = contextvars.ContextVar('current_user_id', default=None)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('binentor.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, api_key TEXT, secret_key TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS memory
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT)''')

    conn.commit()
    conn.close()

init_db()


def has_keys(user_id):
    conn = sqlite3.connect('binentor.db')
    row = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def get_client(user_id):
    conn = sqlite3.connect('binentor.db')
    row = conn.execute("SELECT api_key, secret_key FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()

    if row:
        return BinanceClient(row[0], row[1])
    return None


# --- IMAGE PROCESSING (NO AI) ---
def extract_chart_data(pil_image):
    img = np.array(pil_image)

    # resize
    img = cv2.resize(img, (1024, 1024))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # edge detection
    edges = cv2.Canny(gray, 50, 150)

    # OCR
    text = pytesseract.image_to_string(gray)

    # basic stats
    brightness = np.mean(gray)
    edge_density = np.sum(edges > 0) / edges.size

    return {
        "ocr_text": text.strip(),
        "brightness": round(float(brightness), 2),
        "edge_density": round(float(edge_density), 4)
    }


# --- TOOLS ---
def fetch_balance():
    user_id = current_user_id.get()
    client = get_client(user_id)

    if not client:
        return "No Binance keys."

    try:
        acc = client.get_account()
        balances = [
            f"{b['asset']}: {b['free']}"
            for b in acc['balances']
            if float(b['free']) > 0
        ]
        return "Portfolio:\n" + "\n".join(balances)
    except Exception as e:
        return str(e)


def get_market_price(symbol):
    try:
        client = BinanceClient("", "")
        price = client.get_symbol_ticker(symbol=symbol.upper())
        return f"{symbol.upper()} price: {price['price']}"
    except:
        return "Invalid symbol"


def get_crypto_price_coingecko(coin):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin.lower()}&vs_currencies=usd"
        res = requests.get(url).json()

        if coin.lower() in res:
            price = res[coin.lower()]['usd']
            return f"{coin.upper()} price: ${price}"
        else:
            return "Coin not found."
    except Exception as e:
        return str(e)


def save_note(note):
    user_id = current_user_id.get()
    conn = sqlite3.connect('binentor.db')
    conn.execute("INSERT INTO memory (user_id, note) VALUES (?, ?)", (user_id, note))
    conn.commit()
    conn.close()
    return "Saved."


def read_notes():
    user_id = current_user_id.get()
    conn = sqlite3.connect('binentor.db')
    rows = conn.execute("SELECT note FROM memory WHERE user_id=?", (user_id,)).fetchall()
    conn.close()

    if not rows:
        return "No notes."
    return "Notes:\n" + "\n".join([r[0] for r in rows])


# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are Binentor, a strict trading mentor.

Style:
- Short
- Sharp
- No fluff

Max 4 lines.

Focus:
- Risk
- Execution

Tool usage:
TOOL_CALL: function_name(arg=value)
"""

sessions = {}

# --- TOOL PARSER ---
def parse_tool(text):
    match = re.search(r"TOOL_CALL:\s*(\w+)\((.*?)\)", text)
    if not match:
        return None, {}

    name = match.group(1)
    args_str = match.group(2)

    args = {}
    if args_str:
        for part in args_str.split(","):
            if "=" in part:
                k, v = part.split("=")
                args[k.strip()] = v.strip().strip('"')

    return name, args


def execute_tool(name, args):
    if name == "fetch_balance":
        return fetch_balance()
    elif name == "get_market_price":
        return get_market_price(args.get("symbol", ""))
    elif name == "get_crypto_price_coingecko":
        return get_crypto_price_coingecko(args.get("coin", ""))
    elif name == "save_note":
        return save_note(args.get("note", ""))
    elif name == "read_notes":
        return read_notes()

    return "Unknown tool"


# --- HANDLERS ---
ASK_API, ASK_SECRET = range(2)


class NoKeysFilter(filters.MessageFilter):
    def filter(self, message):
        return message and message.from_user and not has_keys(message.from_user.id)


no_keys = NoKeysFilter()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if has_keys(uid):
        await update.message.reply_text("Binentor active.")
        return ConversationHandler.END

    await update.message.reply_text("Send API Key:")
    return ASK_API


async def save_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['api'] = update.message.text
    await update.message.reply_text("Send Secret Key:")
    return ASK_SECRET


async def save_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    api = context.user_data['api']
    secret = update.message.text

    conn = sqlite3.connect('binentor.db')
    conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (uid, api, secret))
    conn.commit()
    conn.close()

    await update.message.reply_text("Keys saved.")
    return ConversationHandler.END


# --- MAIN AI ---
async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    current_user_id.set(uid)

    if uid not in sessions:
        sessions[uid] = chat_model.start_chat(history=[
            {"role": "user", "parts": [SYSTEM_PROMPT]}
        ])

    chat = sessions[uid]

    try:
        user_text = update.message.text
        await update.message.chat.send_action(action=ChatAction.TYPING)

        response = await chat.send_message_async(user_text)
        text = response.text.strip()

        tool, args = parse_tool(text)

        if tool:
            result = execute_tool(tool, args)
            final = await chat.send_message_async(f"Tool result: {result}")
            await update.message.reply_text(final.text)
        else:
            await update.message.reply_text(text)

    except Exception as e:
        logger.error(e)
        await update.message.reply_text(f"Error: {e}")


# --- IMAGE HANDLER (NO VISION) ---
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    current_user_id.set(uid)

    photo = await update.message.photo[-1].get_file()
    buf = io.BytesIO()
    await photo.download_to_memory(buf)

    img = Image.open(buf)

    await update.message.chat.send_action(action=ChatAction.TYPING)

    data = extract_chart_data(img)

    prompt = f"""
Chart Data:
OCR: {data['ocr_text']}
Brightness: {data['brightness']}
Edge Density: {data['edge_density']}

Task:
- Is this a trading chart?
- If yes: trend + bias (LONG/SHORT/WAIT)

Max 4 lines.
"""

    res = await chat_model.generate(prompt)

    await update.message.reply_text(res.text)


# --- MAIN ---
if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(no_keys & filters.TEXT, start)
        ],
        states={
            ASK_API: [MessageHandler(filters.TEXT, save_api)],
            ASK_SECRET: [MessageHandler(filters.TEXT, save_secret)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))

    logger.info("Binentor running (NO VISION MODE)...")
    app.run_polling()
