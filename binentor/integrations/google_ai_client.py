import google.generativeai as genai
from typing import Optional
from binentor.config.settings import GOOGLE_API_KEY

# Configure the Google AI SDK
genai.configure(api_key=GOOGLE_API_KEY)

# Use the latest model version
model = genai.GenerativeModel("gemma-3-27b-it")


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
    Clean up LLM output for the Telegram interface.
    """
    if not response_text:
        return "Something went wrong. Try again."

    text = response_text.strip()

    # Remove bad markdown patterns that look messy in chat
    banned_patterns = ["```", "###", "##", "# ", "> "]
    for pattern in banned_patterns:
        text = text.replace(pattern, "")

    # Safety trim to prevent message overflow
    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."

    return text


async def generate_response(
    system_prompt: str,
    user_message: str,
    user_id: Optional[str] = None,
) -> str:
    """
    Main function used by the agent to generate content.
    """
    try:
        # Build the structured prompt
        prompt = _build_prompt(system_prompt, user_message)

        # Call the model
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 1024,
            }
        )

        # Process and return the final text
        return _post_process(response.text)

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return "I'm having a bit of trouble thinking right now. Give me a moment."
