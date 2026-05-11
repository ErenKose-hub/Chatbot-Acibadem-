"""
llm_service.py — Ollama LLM bağlantı yöneticisi.

Tüm Ollama HTTP çağrıları bu modül üzerinden yapılır.
Model adı ve URL ortam değişkenlerinden okunur.
"""

import os
import requests

OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://acu-llm:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

# Varsayılan model seçenekleri
DEFAULT_OPTIONS: dict = {
    "temperature": 0.1,
    "num_ctx": 8192,
    "num_predict": 300,
}


def ask_llm(
    system_prompt: str,
    messages: list[dict],
    options: dict | None = None,
    timeout: int = 180,
) -> str:
    """
    Ollama /api/chat endpoint'ine istek atar.

    Args:
        system_prompt: Sistem talimatları.
        messages: [{"role": "user"/"assistant", "content": "..."}, ...] listesi.
        options: Ollama model seçenekleri (opsiyonel; varsayılanlar kullanılır).
        timeout: HTTP istek zaman aşımı (saniye).

    Returns:
        Modelin ürettiği metin; hata durumunda Türkçe hata mesajı.
    """
    merged_options = {**DEFAULT_OPTIONS, **(options or {})}
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "stream": False,
        "options": merged_options,
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get(
            "content", "Üzgünüm, şu an yanıt veremiyorum."
        ).strip()
    except requests.exceptions.ConnectionError:
        print(f"[LLMService] Bağlantı hatası: {OLLAMA_BASE_URL}")
        return "⚠️ LLM Bağlantı Hatası: Ollama servisine ulaşılamıyor. Lütfen sistem yöneticisine başvurun."
    except Exception as e:
        print(f"[LLMService] Beklenmedik hata: {e}")
        return f"⚠️ LLM Beklenmedik Hata: İstek işlenirken bir sorun oluştu. (Detay: {str(e)})"


def generate_llm(
    prompt: str,
    options: dict | None = None,
    timeout: int = 120,
) -> str:
    """
    Ollama /api/generate endpoint'ine istek atar (chat_api için).

    Args:
        prompt: Tam prompt metni (system + context + soru dahil).
        options: Ollama model seçenekleri (opsiyonel).
        timeout: HTTP istek zaman aşımı (saniye).

    Returns:
        Modelin ürettiği metin; hata durumunda Türkçe hata mesajı.
    """
    merged_options = {"temperature": 0.1, "num_predict": 300, **(options or {})}
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": merged_options,
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "Üzgünüm, yanıt veremiyorum.").strip()
    except requests.exceptions.ConnectionError:
        print(f"[LLMService] Bağlantı hatası: {OLLAMA_BASE_URL}")
        return "⚠️ LLM Bağlantı Hatası: Ollama servisine ulaşılamıyor."
    except Exception as e:
        print(f"[LLMService] Beklenmedik hata: {e}")
        return f"⚠️ LLM Beklenmedik Hata: (Detay: {str(e)})"


def check_ollama_health() -> bool:
    """
    Ollama servisinin erişilebilir olup olmadığını kontrol eder.
    /api/tags endpoint'ine GET isteği atar.

    Returns:
        True → servis ayakta; False → ulaşılamıyor.
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
