import os
import io
import re
import logging
import sqlite3
import contextvars
from PIL import Image

from telegram import Update, constants, ReplyKeyboardRemove
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
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

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


# --- AI ---
SYSTEM_PROMPT = """
You are Binentor, a strict trading mentor.

Rules:
- Be sharp, direct, logical.
- Focus on discipline, risk, mistakes.

When you need a tool, respond ONLY like:

TOOL_CALL: function_name(arg=value)

Functions:
- fetch_balance()
- get_market_price(symbol)
- save_note(note)
- read_notes()

Otherwise respond normally.
"""

model = genai.GenerativeModel(
    model_name="gemma-3-27b-it",
    system_instruction=SYSTEM_PROMPT
)

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
        parts = args_str.split(",")
        for p in parts:
            if "=" in p:
                k, v = p.split("=")
                args[k.strip()] = v.strip().strip('"')

    return name, args


def execute_tool(name, args):
    if name == "fetch_balance":
        return fetch_balance()

    elif name == "get_market_price":
        return get_market_price(args.get("symbol", ""))

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


async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    current_user_id.set(uid)

    if uid not in sessions:
        sessions[uid] = model.start_chat()

    chat = sessions[uid]

    try:
        user_text = update.message.text
        response = await chat.send_message_async(user_text)

        text = response.text

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


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = await update.message.photo[-1].get_file()
    buf = io.BytesIO()
    await photo.download_to_memory(buf)

    img = Image.open(buf)

    vision = genai.GenerativeModel("gemini-1.5-pro")

    res = await vision.generate_content_async(["Analyze this chart", img])
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
        fallbacks=[]
    )

    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT, main_handler))

    logger.info("Bot running...")
    app.run_polling()
