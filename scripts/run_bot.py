import os
import io
import logging
import sqlite3
import contextvars
from PIL import Image
from cryptography.fernet import Fernet
from telegram import Update, constants, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)
from binance.client import Client as BinanceClient
import google.generativeai as genai

# --- 1. CONFIGURATION & SECURITY ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Env Vars
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY environment variable is missing!")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())
current_user_id = contextvars.ContextVar('current_user_id', default=None)

# --- 2. DATABASE & MEMORY LAYER ---
def init_db():
    conn = sqlite3.connect('claw_mentor.db')
    c = conn.cursor()
    # User Credentials
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, api_key BLOB, secret_key BLOB)''')
    # Long-term Mentorship Memory
    c.execute('''CREATE TABLE IF NOT EXISTS memory 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, note TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_binance_client(user_id):
    conn = sqlite3.connect('claw_mentor.db')
    c = conn.cursor()
    c.execute("SELECT api_key, secret_key FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        try:
            api = cipher_suite.decrypt(row[0]).decode()
            secret = cipher_suite.decrypt(row[1]).decode()
            return BinanceClient(api, secret)
        except Exception as e:
            logger.error(f"Decryption error for user {user_id}: {e}")
    return None

# --- 3. AI AGENT TOOLS ---

def fetch_balance() -> str:
    """Check the user's current Binance spot balances."""
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
    """Get real-time price for any pair (e.g. BTCUSDT)."""
    user_id = current_user_id.get()
    client = get_binance_client(user_id) or BinanceClient("", "") # Public data doesn't need keys
    try:
        ticker = client.get_symbol_ticker(symbol=symbol.upper())
        return f"The current price of {symbol.upper()} is {ticker['price']}"
    except:
        return f"Could not find price for {symbol}."

def save_mentor_note(note: str) -> str:
    """Saves a lesson, mistake, or goal to the user's long-term profile."""
    user_id = current_user_id.get()
    conn = sqlite3.connect('claw_mentor.db')
    conn.cursor().execute("INSERT INTO memory (user_id, note) VALUES (?, ?)", (user_id, note))
    conn.commit()
    conn.close()
    return "Note saved to long-term memory."

def read_mentor_notes() -> str:
    """Retrieves all past lessons and notes for this user."""
    user_id = current_user_id.get()
    conn = sqlite3.connect('claw_mentor.db')
    rows = conn.cursor().execute("SELECT note FROM memory WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return "User History/Notes: " + "; ".join([r[0] for r in rows]) if rows else "No previous notes."

# --- 4. AI CONFIGURATION ---
genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """
You are Claw-Mentor, a elite quantitative analyst and Socratic trading coach.
1. PERSONALIZED: Use the 'read_mentor_notes' tool at the start of conversations to remember who the user is.
2. AGENTIC: Use Binance tools automatically to answer questions about prices or balances.
3. SOCRATIC: If a user wants to trade, ask for their 'Stop Loss', 'Take Profit', and 'Thesis'. Never let them gamble.
4. SECURITY: Remind users never to share their secret keys with humans.
5. TONE: Professional, sharp, and focused on Risk Management.
"""

ai_model = genai.GenerativeModel(
    model_name='gemini-1.5-pro',
    tools=[fetch_balance, get_market_price, save_mentor_note, read_mentor_notes],
    system_instruction=SYSTEM_INSTRUCTION
)

user_sessions = {}

# --- 5. TELEGRAM HANDLERS ---
# States for Onboarding Conversation
ASK_API, ASK_SECRET = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    client = get_binance_client(user_id)
    
    if client:
        await update.message.reply_text("🛡️ **Claw-Mentor Active.**\nI have your keys secured. What are we analyzing today?")
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "👋 **I am Claw-Mentor.** To begin, I need Read-Only access to your Binance.\n\n"
            "1. Go to Binance API Management.\n"
            "2. Create a key. **DISABLE 'Withdrawals' and 'Spot Trading'.** Only 'Enable Reading'.\n"
            "3. Send me your **API Key** now (or /cancel):"
        )
        return ASK_API

async def handle_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tmp_api'] = update.message.text
    await update.message.reply_text("Got it. Now send your **Secret Key** (this will be encrypted immediately):")
    return ASK_SECRET

async def handle_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    api_key = context.user_data['tmp_api']
    secret_key = update.message.text
    
    # Encrypt and Save
    enc_api = cipher_suite.encrypt(api_key.encode())
    enc_secret = cipher_suite.encrypt(secret_key.encode())
    
    conn = sqlite3.connect('claw_mentor.db')
    conn.cursor().execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, enc_api, enc_secret))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("✅ **Connection Secured.** I can now see your charts and balance. Ask me anything!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Onboarding cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    current_user_id.set(user_id)
    
    await update.message.reply_chat_action(constants.ChatAction.TYPING)
    
    if user_id not in user_sessions:
        user_sessions[user_id] = ai_model.start_chat(enable_automatic_function_calling=True)

    try:
        response = await user_sessions[user_id].send_message_async(user_text)
        await update.message.reply_text(response.text, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"AI Error: {e}")
        await update.message.reply_text("I hit a logic error. Try rephrasing or check your API permissions.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_user_id.set(user_id)
    await update.message.reply_chat_action(constants.ChatAction.TYPING)

    photo = await update.message.photo[-1].get_file()
    buf = io.BytesIO()
    await photo.download_to_memory(buf)
    img = Image.open(buf)

    prompt = "Examine this chart. Identify trend, support, resistance, and provide a mentorship-style critique."
    
    try:
        # Vision uses a fresh call to ensure image processing is handled correctly
        vision_model = genai.GenerativeModel('gemini-1.5-pro', system_instruction=SYSTEM_INSTRUCTION)
        response = await vision_model.generate_content_async([prompt, img])
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Analysis failed: {e}")

# --- 6. EXECUTION ---
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    onboarding_conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ASK_API: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_key)],
            ASK_SECRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_secret_key)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(onboarding_conv)
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))

    logger.info("Claw-Mentor Genius Edition Online.")
    app.run_polling()
