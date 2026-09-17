from dotenv import load_dotenv
from openai import OpenAI
import os
from functools import lru_cache

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    # Construct lazily so importing the package does not require an API key.
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def call_openai_model(user_input, tool_schemas=None, raw_response=True):
    request = {
        "model":MODEL,
        # "reasoning":{"effort" : "none"},
        "input":user_input,
    }

    if tool_schemas is not None:
        request["tools"]=tool_schemas

    response = get_client().responses.create(
        **request
    )

    if raw_response:
        return response

    return response.output_text

