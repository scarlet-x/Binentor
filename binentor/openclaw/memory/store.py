import threading

_lock = threading.Lock()

# user_id -> data
_user_store = {}


def set_user_keys(user_id: str, api_key: str, secret_key: str):

    with _lock:
        if user_id not in _user_store:
            _user_store[user_id] = {}

        _user_store[user_id]["binance_api_key"] = api_key
        _user_store[user_id]["binance_secret_key"] = secret_key


def get_user_keys(user_id: str):

    with _lock:
        user = _user_store.get(user_id)

        if not user:
            return None

        return {
            "api_key": user.get("binance_api_key"),
            "secret_key": user.get("binance_secret_key"),
        }


def set_memory(user_id: str, key: str, value):

    with _lock:
        if user_id not in _user_store:
            _user_store[user_id] = {}

        _user_store[user_id][key] = value


def get_memory(user_id: str):

    with _lock:
        return _user_store.get(user_id, {})
