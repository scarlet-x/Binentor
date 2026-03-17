import threading

# A lock ensures that multiple threads (from the Telegram bot) 
# don't try to write to the store at the exact same time.
_lock = threading.Lock()

# user_id -> dict of data
_user_store = {}


def set_user_keys(user_id: str, api_key: str, secret_key: str):
    """
    Securely stores the user's Binance API credentials in memory.
    """
    with _lock:
        if user_id not in _user_store:
            _user_store[user_id] = {}

        _user_store[user_id]["binance_api_key"] = api_key
        _user_store[user_id]["binance_secret_key"] = secret_key


def get_user_keys(user_id: str):
    """
    Retrieves the Binance API credentials for a specific user.
    Returns a dictionary or None if keys aren't set.
    """
    with _lock:
        user = _user_store.get(user_id)

        if not user:
            return None

        return {
            "api_key": user.get("binance_api_key"),
            "secret_key": user.get("binance_secret_key"),
        }


def set_memory(user_id: str, key: str, value):
    """
    Generic function to store any specific piece of data for a user.
    """
    with _lock:
        if user_id not in _user_store:
            _user_store[user_id] = {}

        _user_store[user_id][key] = value


def get_memory(user_id: str):
    """
    Retrieves all stored information for a specific user.
    """
    with _lock:
        return _user_store.get(user_id, {})
