"""
views.py — Acıbadem Üniversitesi Chatbot View Katmanı

Bu dosya yalnızca HTTP request/response döngüsünü yönetir.
Tüm iş mantığı chat/services/ altındaki modüllerde yaşar:
  - direct_answer  : Basit sorulara anında yanıt (LLM çağrısı yok)
  - rag_service    : ChromaDB sorgulama + Strict Bölüm Filtreleme
  - prompt_manager : Sistem promptları ve yanıt temizleme
  - llm_service    : Ollama HTTP çağrıları
"""

import json
from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
from django.views.decorators.csrf import csrf_exempt

from .models import ChatMessage
from .vector_store import get_chroma_collection
from .services.direct_answer import check_direct_answer
from .services.rag_service import build_context
from .services.prompt_manager import build_system_prompt, build_api_prompt, clean_bot_response
from .services.llm_service import ask_llm, generate_llm, check_ollama_health, OLLAMA_MODEL, OLLAMA_BASE_URL


# ---------------------------------------------------------------------------
# Yardımcı: Keyword kontrolü (chat_api hibrit karar için)
# ---------------------------------------------------------------------------

_PRIORITY_KEYWORDS = [
    "kontenjan", "puan", "ucret", "burs", "siralam",
    "muhendislik", "tip", "eczacilik",
]


def _has_priority_keyword(normalized_text: str) -> bool:
    return any(kw in normalized_text for kw in _PRIORITY_KEYWORDS)


def _normalize(text: str) -> str:
    text = text.lower()
    for src, dst in [("ı", "i"), ("ü", "u"), ("ö", "o"), ("ş", "s"), ("ç", "c"), ("ğ", "g")]:
        text = text.replace(src, dst)
    return text


# ---------------------------------------------------------------------------
# View: Sağlık Kontrolü — /health/
# ---------------------------------------------------------------------------

def health_check(request):
    """
    Tüm bağımlılıkların durumunu kontrol edip JSON döndürür.

    Response örneği:
        {
            "status": "ok",
            "postgres": "ok",
            "chromadb": "ok",
            "ollama": "ok",
            "model": "qwen2.5:3b"
        }
    """
    result = {}

    # 1. PostgreSQL
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        result["postgres"] = "ok"
    except Exception as e:
        result["postgres"] = f"error: {e}"

    # 2. ChromaDB
    try:
        col = get_chroma_collection()
        doc_count = col.count()
        result["chromadb"] = f"ok ({doc_count} doküman)"
    except Exception as e:
        result["chromadb"] = f"error: {e}"

    # 3. Ollama
    result["ollama"] = "ok" if check_ollama_health() else f"error: {OLLAMA_BASE_URL} ulaşılamıyor"
    result["model"] = OLLAMA_MODEL

    # Genel durum
    has_error = any("error" in str(v) for v in result.values())
    result["status"] = "degraded" if has_error else "ok"

    status_code = 200 if result["status"] == "ok" else 503
    return JsonResponse(result, status=status_code)


# ---------------------------------------------------------------------------
# View: Ana Sohbet — /
# ---------------------------------------------------------------------------

def chat_home(request):
    """Ana sohbet arayüzünü yöneten view."""
    if request.method == "GET":
        request.session["chat_history"] = []
    elif "chat_history" not in request.session:
        request.session["chat_history"] = []

    if request.method == "POST":
        user_text = request.POST.get("message", "").strip()

        # ── 1. DIRECT ANSWER KONTROLÜ (TEST İÇİN DEVRE DIŞI) ───────────────────
        # direct = check_direct_answer(user_text)
        # if direct:
        #     return JsonResponse({
        #         "response": direct
        #     })
        
        # ── 2. RAG: ChromaDB + Strict Bölüm Filtreleme ───────────────────────
        fresh_context, sources = build_context(user_text)

        if not fresh_context:
            return JsonResponse({
                "response": (
                    "Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde "
                    "güncel bir veri bulunmamaktadır. "
                    "Lütfen aday öğrenci sayfasını (aday.acibadem.edu.tr) ziyaret edin."
                )
            })

        # ── 3. KONUŞMA GEÇMİŞİ VE MESAJ LİSTESİ ────────────────────────────────
        history = request.session["chat_history"]

        # ── 4. SİSTEM PROMPT'U ────────────────────────────────────────────────
        system_prompt = build_system_prompt(fresh_context)

        messages = []
        # Sadece son 3 konuşmayı (6 mesaj) LLM'e ver
        for chat in history[-3:]:
            messages.append({"role": "user", "content": chat["user"]})
            messages.append({"role": "assistant", "content": chat["bot"]})
            
        messages.append({"role": "user", "content": user_text})

        # ── 6. LLM ÇAĞRISI ───────────────────────────────────────────────────
        print("\n=== [DEBUG] LLM PAYLOAD ===")
        print(f"System Prompt:\n{system_prompt}")
        print(f"Messages:\n{messages}")
        print("===========================\n")
        bot_response = ask_llm(system_prompt, messages)
        bot_response = clean_bot_response(bot_response)

        if sources:
            source_note = "\n\n(Kaynak: " + ", ".join(sources) + ")"
            print(f"[RAG] Kullanılan Kaynaklar: {sources}")
            bot_response += source_note

        # ── 7. GEÇMİŞ & VERİTABANI KAYDI ────────────────────────────────────
        history.append({"user": user_text, "bot": bot_response})
        request.session["chat_history"] = history
        request.session.modified = True
        ChatMessage.objects.create(user_message=user_text, bot_response=bot_response)

        return JsonResponse({"response": bot_response})

    return render(request, "chat/index.html")


# ---------------------------------------------------------------------------
# View: Harici API — /api/chat/
# ---------------------------------------------------------------------------

@csrf_exempt
def chat_api(request):
    """Harici API istemcileri için JSON tabanlı endpoint (hibrit filtreleme ile)."""
    if request.method != "POST":
        return JsonResponse({"error": "Sadece POST destekleniyor."}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Geçersiz JSON formatı."}, status=400)

    user_text = data.get("message", "").strip()
    if not user_text:
        return JsonResponse({"error": "Mesaj boş olamaz."}, status=400)

    # ── 1. DIRECT ANSWER KONTROLÜ (TEST İÇİN DEVRE DIŞI) ───────────────────
    # direct = check_direct_answer(user_text)
    # if direct:
    #     return JsonResponse({"response": direct})

    # ── 2. RAG VE LLM ÇAĞRISI ───────────────────────────────────────────────
    fresh_context, sources = build_context(user_text)
    
    if not fresh_context:
        return JsonResponse({
            "response": (
                "Üzgünüm, aradığınız konu hakkında sistemimde güncel bir veri bulunmamaktadır."
            )
        })

    # ── 3. PROMPT & LLM ──────────────────────────────────────────────────────
    full_prompt = build_api_prompt(fresh_context, user_text)
    print("\n=== [DEBUG] LLM PAYLOAD (API) ===")
    print(f"Full Prompt:\n{full_prompt}")
    print("=================================\n")
    bot_response = generate_llm(full_prompt)
    bot_response = clean_bot_response(bot_response)

    if sources:
        source_note = "\n\n(Kaynak: " + ", ".join(sources) + ")"
        print(f"[RAG API] Kullanılan Kaynaklar: {sources}")
        bot_response += source_note

    ChatMessage.objects.create(user_message=user_text, bot_response=bot_response)
    return JsonResponse({"response": bot_response})