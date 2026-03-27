from __future__ import annotations
import os
import json
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
import logging
logger = logging.getLogger(__name__)
from config import LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503)
    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout))

class LLMClient:

    def __init__(self) -> None:
        self.base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
        self.api_key = os.getenv('OPENAI_API_KEY', '')
        self.model = LLM_MODEL
        self.temperature = LLM_TEMPERATURE
        self.max_tokens = LLM_MAX_TOKENS
        self._client = httpx.Client(timeout=20.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2.0), retry=retry_if_exception(_is_retryable))
    def chat(self, task_id: str, messages: list[dict]) -> str:
        headers = {'Content-Type': 'application/json', 'IWA-Task-ID': task_id}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        body = {'model': self.model, 'messages': messages, 'temperature': self.temperature, 'max_tokens': self.max_tokens}
        resp = self._client.post(f'{self.base_url}/chat/completions', json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']