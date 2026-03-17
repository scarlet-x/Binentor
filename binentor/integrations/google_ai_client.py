import google.generativeai as genai
from typing import Optional
from binentor.config.settings import GOOGLE_API_KEY

genai.configure(api_key=GOOGLE_API_KEY)

# Use a fast + controllable model
model = genai.GenerativeModel("gemma-3-27b-it")


def _build_prompt(system_prompt: str, user_message: str) -> str:
    """
    Combines system personality + user input cleanly.
    This lets the `system_prompt` entirely dictate how the bot acts, 
    allowing it to respond dynamically based on the context you pass to it.
    """
    if system_prompt:
        return f"{system_prompt.strip()}\n\nUser: {user_message.strip()}\nBot:"
    
    return user_message.strip()


def _post_process(response_text: str) -> str:
    """
    Clean up LLM output without destroying useful formatting.
    """
    if not response_text:
        return "Something went wrong. Try again."

    # Simply clean up extra whitespace. We leave Markdown intact so the 
    # bot can use lists, code blocks, and bold text when necessary.
    return response_text.strip()


async def generate_response(
    system_prompt: str,
    user_message: str,
    user_id: Optional[str] = None,
    max_tokens: int = 1500,  # Increased default so the bot isn't cut off
    temperature: float = 0.7 # Made dynamic if you want to change it later
) -> str:
    """
    Main function used by the agent.
    """
    try:
        prompt = _build_prompt(system_prompt, user_message)

        # Using the async version of generate_content for better performance
        response = await model.generate_content_async(
            prompt,
            generation_config={
                "temperature": temperature,     
                "top_p": 0.9,
                "max_output_tokens": max_tokens
            },
        )

        text = response.text if hasattr(response, "text") else None

        return _post_process(text)

    except Exception as e:
        return f"Error: {str(e)}"
