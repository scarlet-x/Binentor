from pathlib import Path
from binentor.integrations.google_ai_client import generate_response
from binentor.openclaw.memory.store import get_user_keys
from binance.client import AsyncClient
from binance.exceptions import BinanceAPIException

PERSONALITY_PATH = Path(__file__).resolve().parents[1] / "prompts" / "personality.md"


def load_personality():
    with open(PERSONALITY_PATH, "r", encoding="utf-8") as f:
        return f.read()


PERSONALITY = load_personality()


async def get_binance_data(api_key: str, secret_key: str, message: str) -> str:
    """
    Checks the user's message intent and fetches relevant Binance data.
    """
    msg_lower = message.lower()
    context_data = []
    
    try:
        # We use AsyncClient so it doesn't block the Telegram event loop
        client = await AsyncClient.create(api_key, secret_key)
        
        # 1. Fetch Balances if the prompt implies portfolio checks or trading decisions
        balance_keywords = ['balance', 'portfolio', 'holdings', 'funds', 'wallet', 'asset', 'btc', 'eth', 'usdt', 'bnb', 'buy', 'sell', 'account', 'have']
        if any(k in msg_lower for k in balance_keywords):
            account = await client.get_account()
            balances = account.get('balances', [])
            active_balances = [b for b in balances if float(b['free']) > 0 or float(b['locked']) > 0]
            
            if active_balances:
                bal_str = "[Current Wallet Balances]\n" + "\n".join([f"- {b['asset']}: {b['free']} (Free), {b['locked']} (Locked)" for b in active_balances])
                context_data.append(bal_str)
            else:
                context_data.append("[Current Wallet Balances]\nAccount is currently empty.")

        # 2. Fetch Open Orders if the prompt mentions them
        order_keywords = ['order', 'open', 'limit', 'cancel', 'pending']
        if any(k in msg_lower for k in order_keywords):
            orders = await client.get_open_orders()
            if orders:
                ord_str = "[Open Orders]\n" + "\n".join([f"- {o['symbol']}: {o['side']} {o['origQty']} at {o['price']}" for o in orders])
                context_data.append(ord_str)
            else:
                context_data.append("[Open Orders]\nNo open orders right now.")

        # Close async connection gracefully
        await client.close_connection()

    except BinanceAPIException as e:
        context_data.append(f"[Binance API Error]: {e.message} (Inform the user their API key might lack permissions or is invalid)")
    except Exception as e:
        context_data.append(f"[System Error]: Could not fetch Binance data. {str(e)}")

    if context_data:
        return "\n\n--- USER'S LIVE BINANCE DATA ---\n" + "\n\n".join(context_data)
    
    return ""


async def run_agent(user_id: str, message: str):
    system_prompt = PERSONALITY
    keys = get_user_keys(user_id)
    
    # If the user has connected keys, fetch context and append it to the prompt
    if keys and keys.get("api_key") and keys.get("secret_key"):
        binance_context = await get_binance_data(keys["api_key"], keys["secret_key"], message)
        
        if binance_context:
            # We silently attach the context to the message going to the LLM
            message = f"{message}\n{binance_context}\n\n(Note to AI: Use the above live Binance data to provide accurate, personalized guidance to the user. Do not leak the raw JSON, just reference their assets naturally.)"

    response = await generate_response(
        system_prompt=system_prompt,
        user_message=message,
        user_id=user_id,
    )

    return response
