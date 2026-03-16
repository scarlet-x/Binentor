from binentor.integrations.google_ai_client import generate_response


SYSTEM_PROMPT = """
You are Binentor, a smart Binance trading mentor.

Explain the WHY behind trading decisions.
Help the user become a better trader.

Be clear, helpful, and concise.
"""


class GeneralSkill:

    async def execute(self, message, memory):

        prompt = f"""
{SYSTEM_PROMPT}

User message:
{message}

User context:
{memory}
"""

        response = generate_response(prompt)

        return {
            "response": response
        }
