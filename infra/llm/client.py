from functools import wraps
import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class LLMClient:
    _instance = None

    def __init__(self):
        from openai import OpenAI
        from config import get_settings
        s = get_settings()
        self._client = OpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def chat(self, model, messages, response_format=None, timeout=60, temperature=None, max_tokens=None):
        kwargs = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
        }
        if response_format:
            kwargs["response_format"] = response_format
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return self._client.chat.completions.create(**kwargs)


def get_llm_client():
    return LLMClient.get_instance()
