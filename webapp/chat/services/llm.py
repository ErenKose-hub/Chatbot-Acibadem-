import logging
import os
import time

import requests

# Docker içinden Mac host'undaki (lokal) Ollama'ya erişmek için 'host.docker.internal' kullanılır.
# Eğer Docker dışında çalıştırıyorsan 'http://localhost:11434' yapabilirsin.
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
logger = logging.getLogger(__name__)


def call_ollama_chat(system_instructions: str, messages: list[dict]) -> str:
    started_at = time.perf_counter()
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "system", "content": system_instructions}] + messages,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "repeat_penalty": 1.2,
                "num_predict": 1024
            },
        },
        timeout=180,
    )
    response.raise_for_status()
    logger.info(
        "Ollama chat completed in %.2fs with model %s",
        time.perf_counter() - started_at,
        OLLAMA_MODEL,
    )
    return response.json().get("message", {}).get(
        "content", "Üzgünüm, şu an yanıt veremiyorum."
    ).strip()


def list_ollama_models() -> list[str]:
    response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
    response.raise_for_status()
    return [item.get("name") for item in response.json().get("models", [])]
