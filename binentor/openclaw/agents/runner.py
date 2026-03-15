from binentor.openclaw.routing.router import route_skill
from binentor.openclaw.memory.store import get_memory, update_memory


async def run_agent(user_id: str, message: str):

    memory = get_memory(user_id)

    skill = route_skill(message)

    result = await skill.execute(message, memory)

    if result.get("memory_update"):
        update_memory(user_id, result["memory_update"])

    return result["response"]
