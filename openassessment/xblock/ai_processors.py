from django.conf import settings
import openai

def get_openai_key():
    return settings.OPENAI_API_KEY if hasattr(settings, 'OPENAI_API_KEY') else None

def davinci_model_processor(question: str, messages: list = []) -> str:
    """
    The davinci AI processor
    """
    openai.api_key = get_openai_key()
    if openai.api_key:
        return openai.Completion.create(
            engine="text-davinci-003",
            # engine="gpt-3.5-turbo",
            prompt=question,
            max_tokens=500,  # TODO: move to settings and get from there. Use automatic tokens counter - https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken
            stop=["    "],
            temperature=1,
        ).choices[0].text
    return "OpenAI API key not set."


def gpt_model_processor(question: str, messages: list = []) -> str:
    """
    The Chat-GPT AI processor
    """
    openai.api_key = get_openai_key()
    if openai.api_key:
        if not messages:
            messages = [{"role": "user", "content": question}]

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=1000,
            stop=["    "],
            temperature=0.7,
        )
        return completion.choices[0].message["content"]
    return "OpenAI API key not set."
