memory_db = {}


def get_memory(user_id):

    if user_id not in memory_db:
        memory_db[user_id] = {}

    return memory_db[user_id]


def update_memory(user_id, new_data):

    if user_id not in memory_db:
        memory_db[user_id] = {}

    memory_db[user_id].update(new_data)
