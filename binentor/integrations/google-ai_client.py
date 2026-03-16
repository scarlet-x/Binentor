import google.generativeai as genai
from binentor.config.settings import GOOGLE_API_KEY

genai.configure(api_key=GOOGLE_API_KEY)

MODEL_NAME = "gemma-3-27b-it"

model = genai.GenerativeModel(MODEL_NAME)


def generate_response(prompt: str) -> str:
    """
    Sends prompt to Gemini and returns response text
    """

    response = model.generate_content(prompt)

    if hasattr(response, "text"):
        return response.text

    return "Sorry, I couldn't generate a response."
