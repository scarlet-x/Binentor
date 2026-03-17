import google.generativeai as genai
from typing import Optional
from binentor.config.settings import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

# Use a fast + controllable model
model = genai.GenerativeModel("gemini-1.5-flash")


def _build_prompt(system_prompt: str, user_message: str) -> str:
    """
    Combines system personality + user input into a structured prompt.
    """

    return f"""
{system_prompt}

---

User says:
{user_message}

---

Instructions:
- Follow the personality strictly
- Keep responses short and human
- Avoid long explanations unless asked
- No markdown abuse (no #, >, etc.)
- Give practical, mentor-style answers
"""


def _post_process(response_text: str, max_length: int = 900) -> str:
    """
    Clean up LLM output.
    """

    if not response_text:
        return "Something went wrong. Try again."

    text = response_text.strip()

    # Remove bad markdown patterns
    banned_patterns = ["```", "###", "##", "# ", "> "]
    for pattern in banned_patterns:
        text = text.replace(pattern, "")

    # Hard trim (safety)
    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."

    return text


async def generate_response(
    system_prompt: str,
    user_message: str,
    user_id: Optional[str] = None,
) -> str:
    """
    Main function used by the agent.
    """

    try:
        prompt = _build_prompt(system_prompt, user_message)

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,     # balanced creativity
                "top_p": 0.9,
                "max_output_tokens": 300,  # controls length
            },
        )

        text = response.text if hasattr(response, "text") else None

        return _post_process(text)

    except Exception as e:
        return f"Error: {str(e)}"
