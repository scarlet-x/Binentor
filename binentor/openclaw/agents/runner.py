from binentor.openclaw.routing.router import route_skill
from binentor.openclaw.memory.store import get_memory


async def run_agent(user_id: str, message: str):

    memory = get_memory(user_id)

    skill = route_skill(message)

    result = await skill.execute(message, memory)

    return result["response"]
