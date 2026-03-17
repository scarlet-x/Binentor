import os
import io
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

# --- 1. CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Env Vars - Ensure these are set in your environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

# Context variable to track which user is currently triggering the AI tools
current_user_id = contextvars.ContextVar('current_user_id', default=None)

# --- 2. DATABASE & MEMORY LAYER ---
def init_db():
    conn = sqlite3.connect('binentor.db')
    c = conn.cursor()
    # User Credentials
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, api_key TEXT, secret_key TEXT)''')
    # Long-term Mentorship Memory
    c.execute('''CREATE TABLE IF NOT EXISTS memory 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT)''')
    conn.commit()
    conn.close()

init_db()

def has_keys(user_id) -> bool:
    """Check if the user has provided keys."""
    conn = sqlite3.connect('binentor.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_binance_client(user_id):
    """Returns a Binance client for the specific user."""
    conn = sqlite3.connect('binentor.db')
    c = conn.cursor()
    c.execute("SELECT api_key, secret_key FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return BinanceClient(row[0], row[1])
    return None

# --- 3. AI AGENT TOOLS ---

def fetch_balance() -> str:
    """Check user's Binance spot balances."""
    user_id = current_user_id.get()
    client = get_binance_client(user_id)
    if not client: return "Error: No Binance keys linked."
    try:
        acc = client.get_account()
        balances = [b for b in acc['balances'] if float(b['free']) > 0 or float(b['locked']) > 0]
        return f"User Portfolio: {balances}"
    except Exception as e:
        return f"Binance Error: {str(e)}"

def get_market_price(symbol: str) -> str:
    """Get real-time price for a pair."""
    user_id = current_user_id.get()
    client = get_binance_client(user_id) or BinanceClient("", "")
    try:
        ticker = client.get_symbol_ticker(symbol=symbol.upper())
        return f"The current price of {symbol.upper()} is {ticker['price']}"
    except Exception:
        return f"Could not find price for {symbol}."

def save_mentor_note(note: str) -> str:
    """Saves a lesson to user memory."""
    user_id = current_user_id.get()
    conn = sqlite3.connect('binentor.db')
    conn.cursor().execute("INSERT INTO memory (user_id, note) VALUES (?, ?)", (user_id, note))
    conn.commit()
    conn.close()
    return "Note saved."

def read_mentor_notes() -> str:
    """Retrieves past lessons."""
    user_id = current_user_id.get()
    conn = sqlite3.connect('binentor.db')
    rows = conn.cursor().execute("SELECT note FROM memory WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return "User Notes: " + "; ".join([r[0] for r in rows]) if rows else "No previous notes."

# --- 4. AI CONFIGURATION ---
genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """
You are Binentor, an elite trading coach.
1. Use tools to fetch balance or prices automatically.
2. Maintain context using 'read_mentor_notes'.
3. Focus on risk management and discipline.
"""

ai_model = genai.GenerativeModel(
    model_name='gemini-1.5-pro',
    tools=[fetch_balance, get_market_price, save_mentor_note, read_mentor_notes],
    system_instruction=SYSTEM_INSTRUCTION
)

user_sessions = {}

# --- 5. TELEGRAM HANDLERS ---
ASK_API, ASK_SECRET = range(2)

class NoKeysFilter(filters.MessageFilter):
    def filter(self, message):
        if not message or not message.from_user: return False
        return not has_keys(message.from_user.id)

no_keys_filter = NoKeysFilter()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if has_keys(user_id):
        await update.message.reply_text("🛡️ **Binentor Active.**\nHow can I help you today?")
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "👋 **I am Binentor.**\nPlease send your **Binance API Key** to start:"
        )
        return ASK_API

async def handle_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tmp_api'] = update.message.text
    await update.message.reply_text("Received. Now send your **Secret Key**:")
    return ASK_SECRET

async def handle_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    api_key = context.user_data['tmp_api']
    secret_key = update.message.text
    
    conn = sqlite3.connect('binentor.db')
    conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, api_key, secret_key))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("✅ **Keys Saved.** Binentor is ready.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_user_id.set(user_id) 
    
    if user_id not in user_sessions:
        user_sessions[user_id] = ai_model.start_chat(enable_automatic_function_calling=True)

    try:
        response = await user_sessions[user_id].send_message_async(update.message.text)
        
        # We attempt to send with Markdown, but if it fails (due to Gemini's formatting)
        # we fall back to plain text to prevent the "Processing Error" message.
        try:
            await update.message.reply_text(response.text, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(response.text)
            
    except Exception as e:
        logger.error(f"Error in main_handler: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ AI Error: {str(e)}")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_user_id.set(user_id)
    
    photo = await update.message.photo[-1].get_file()
    buf = io.BytesIO()
    await photo.download_to_memory(buf)
    img = Image.open(buf)
    
    try:
        vision_model = genai.GenerativeModel('gemini-1.5-pro', system_instruction=SYSTEM_INSTRUCTION)
        response = await vision_model.generate_content_async(["Analyze this trading chart.", img])
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Error in photo_handler: {e}")
        await update.message.reply_text(f"Analysis failed: {e}")

# --- 6. EXECUTION ---
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    onboarding_conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            MessageHandler(no_keys_filter & (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, start) 
        ],
        states={
            ASK_API: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_key)],
            ASK_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_secret_key)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(onboarding_conv)
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))

    logger.info("Binentor Online.")
    app.run_polling()
