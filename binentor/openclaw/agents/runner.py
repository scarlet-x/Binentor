from pathlib import Path
from binentor.integrations.google_ai_client import generate_response

PERSONALITY_PATH = Path(__file__).resolve().parents[1] / "prompts" / "personality.md"


def load_personality():

    with open(PERSONALITY_PATH, "r", encoding="utf-8") as f:
        return f.read()


PERSONALITY = load_personality()


async def run_agent(user_id: str, message: str):

    system_prompt = PERSONALITY

    response = await generate_response(
        system_prompt=system_prompt,
        user_message=message,
        user_id=user_id,
    )

    return response
