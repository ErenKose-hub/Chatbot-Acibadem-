import json
import logging
import re

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.db.models import Max
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .models import ChatMessage, SyncStatus, UniversityContent
from .services.llm import OLLAMA_MODEL, call_ollama_chat, list_ollama_models
from .services.prompts import NO_DATA_RESPONSE, build_system_prompt
from .services.rag import build_context, direct_answer_from_context, has_priority_keyword
from .services.response_quality import is_bad_bot_response
from .services.text_cleaning import clean_bot_response, is_test_source, normalize_text
from .vector_store import get_chroma_collection

logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 1000
MESSAGE_TOO_LONG_ERROR = f"Mesaj en fazla {MAX_MESSAGE_LENGTH} karakter olabilir."


def persist_chat_message(user_text: str, bot_response: str, history: list, session_key: str = "") -> None:
    history.append({"user": user_text, "bot": bot_response})
    if session_key:
        ChatMessage.objects.create(
            user_message=user_text,
            bot_response=bot_response,
            session_key=session_key,
        )


def validate_user_message(user_text: str) -> str | None:
    if not user_text:
        return "Mesaj boş olamaz."
    if len(user_text) > MAX_MESSAGE_LENGTH:
        return MESSAGE_TOO_LONG_ERROR
    return None


def generate_chat_response(user_text: str, history: list | None = None, session_key: str = "") -> tuple[str, list, list]:
    """Shared RAG + LLM response flow for the web UI and JSON API."""
    history = history or []
    normalized = normalize_text(user_text)
    word_count = len(user_text.split())

    chitchat_words = [
        "selam", "merhaba", "nasilsin", "naber", "hey",
        "merhabalar", "selamlar", "sa", "slm",
    ]
    if normalized in chitchat_words or len(user_text) < 3 or (
        not has_priority_keyword(normalized) and word_count < 3
    ):
        greeting = (
            "Merhaba! Ben Acıbadem Üniversitesi Akademik Asistanıyım. "
            "Size üniversitemiz, akademik programlar veya kontenjanlar "
            "hakkında bilgi verebilirim. Ne öğrenmek istersiniz?"
        )
        persist_chat_message(user_text, greeting, history, session_key=session_key)
        return greeting, history, []

    fresh_context, sources = build_context(user_text)
    if not fresh_context:
        persist_chat_message(user_text, NO_DATA_RESPONSE, history, session_key=session_key)
        return NO_DATA_RESPONSE, history, []

    system_prompt = build_system_prompt(fresh_context)


    bot_response = call_ollama_chat(system_prompt, [{"role": "user", "content": user_text}])
    persist_chat_message(user_text, bot_response, history, session_key=session_key)
    return bot_response, history, sources



    # direct_response = direct_answer_from_context(user_text, fresh_context)
    # if direct_response:
    #     persist_chat_message(user_text, direct_response, history, session_key=session_key)
    #     return direct_response, history, sources

    # messages = []
    # past_convo = "".join(
    #     f"Kullanıcı: {chat['user']}\nAsistan: {chat['bot']}\n"
    #     for chat in history[-3:]
    # )
    # if past_convo:
    #     messages.append({"role": "user", "content": f"Önceki konuşmamız özeti:\n{past_convo}"})
    #     messages.append({"role": "assistant", "content": "Anladım, önceki konuşmalarımızı hatırlayarak net cevaplar vereceğim."})
    # messages.append({"role": "user", "content": user_text})

    # try:
    #     bot_response = call_ollama_chat(build_system_prompt(fresh_context), messages)
    #     bot_response = clean_bot_response(bot_response)
    #     if is_bad_bot_response(bot_response):
    #         logger.warning("Rejected low-quality model response: %s", bot_response[:200])
    #         bot_response = NO_DATA_RESPONSE
    #         sources = []

    #     logger.info("RAG sources used: %s", sources)
    #     persist_chat_message(user_text, bot_response, history, session_key=session_key)
    #     return bot_response, history, sources
    # except Exception as e:
    #     logger.exception("Chat response generation failed: %s", e)
    #     fallback_response = "Şu an sistemimde bir yoğunluk var, lütfen biraz bekleyip tekrar sorunuz."
    #     persist_chat_message(user_text, fallback_response, history, session_key=session_key)
    #     return fallback_response, history, []


def chat_home(request):
    """Main chat interface with sidebar conversation history."""
    session_key = request.session.session_key
    if not session_key:
        request.session.save()
        session_key = request.session.session_key

    # New chat: keep the old session in DB but start a fresh one
    if request.method == "GET" and request.GET.get("new_chat"):
        request.session.cycle_key()
        request.session["chat_history"] = []
        request.session.modified = True
        return redirect("chat_home")

    # Switch to a specific session
    target_session = request.GET.get("session", session_key)

    if request.method == "GET":
        db_messages = list(ChatMessage.objects.filter(session_key=target_session).values("user_message", "bot_response"))
        request.session["chat_history"] = [
            {"user": m["user_message"], "bot": m["bot_response"]} for m in db_messages
        ]
    elif "chat_history" not in request.session:
        request.session["chat_history"] = []

    if request.method == "POST":
        user_text = request.POST.get("message", "").strip()
        validation_error = validate_user_message(user_text)
        if validation_error:
            return JsonResponse({"error": validation_error}, status=400)

        active_session_key = target_session if target_session else session_key

        bot_response, history, sources = generate_chat_response(
            user_text, request.session["chat_history"], session_key=active_session_key
        )
        request.session["chat_history"] = history
        request.session.modified = True

        return JsonResponse({"response": bot_response, "sources": sources})

    # Build conversation list for sidebar (group by session_key, show first user message as title)
    sessions = (
        ChatMessage.objects.values("session_key")
        .annotate(last_message=Max("created_at"))
        .order_by("-last_message")[:20]
    )
    conversation_list = []
    for sess in sessions:
        sk = sess["session_key"]
        if not sk:
            continue
        first_msg = ChatMessage.objects.filter(session_key=sk).order_by("created_at").values_list("user_message", flat=True).first()
        title = (first_msg or "Yeni Sohbet")[:35]
        conversation_list.append({"session_key": sk, "title": title, "active": sk == target_session})

    db_messages = list(ChatMessage.objects.filter(session_key=target_session).values("user_message", "bot_response"))
    return render(request, "chat/index.html", {"chat_messages": db_messages, "conversations": conversation_list, "current_session": target_session})


def mascot_image(request, filename):
    """Serve mascot PNG files to the chat UI."""
    if not re.fullmatch(r"[1-9]\.png", filename):
        raise Http404("Maskot bulunamadi.")

    archive_dir = settings.BASE_DIR / "static" / "mascot"

    image_path = archive_dir / filename
    if not image_path.exists():
        raise Http404("Maskot bulunamadi.")

    return FileResponse(image_path.open("rb"), content_type="image/png")


@csrf_exempt
def chat_api(request):
    """JSON endpoint for external API clients."""
    if request.method != "POST":
        return JsonResponse({"error": "Sadece POST destekleniyor."}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Geçersiz JSON formatı."}, status=400)

    user_text = data.get("message", "").strip()
    validation_error = validate_user_message(user_text)
    if validation_error:
        return JsonResponse({"error": validation_error}, status=400)

    bot_response, _, sources = generate_chat_response(user_text)
    return JsonResponse({"response": bot_response, "sources": sources})


def health_check(request):
    """Quick diagnostics for DB, ChromaDB and Ollama."""
    db_content_count = UniversityContent.objects.count()

    chroma_ok = True
    chroma_count = 0
    try:
        chroma_count = get_chroma_collection().count()
    except Exception as e:
        chroma_ok = False
        logger.exception("Health check ChromaDB failed: %s", e)

    ollama_ok = True
    ollama_models = []
    try:
        ollama_models = list_ollama_models()
    except Exception as e:
        ollama_ok = False
        logger.exception("Health check Ollama failed: %s", e)

    model_ready = OLLAMA_MODEL in ollama_models
    sync_status = SyncStatus.objects.filter(key="default").first()
    sync_ok = bool(sync_status and sync_status.last_success_at and not sync_status.last_error)
    healthy = db_content_count > 0 and chroma_count > 0 and chroma_ok and ollama_ok and model_ready and sync_ok

    return JsonResponse(
        {
            "status": "ok" if healthy else "degraded",
            "database": {
                "ok": True,
                "university_content_count": db_content_count,
            },
            "chroma": {
                "ok": chroma_ok,
                "document_count": chroma_count,
            },
            "ollama": {
                "ok": ollama_ok,
                "model": OLLAMA_MODEL,
                "model_ready": model_ready,
                "models": ollama_models,
            },
            "sync": {
                "ok": sync_ok,
                "last_started_at": sync_status.last_started_at.isoformat() if sync_status and sync_status.last_started_at else None,
                "last_success_at": sync_status.last_success_at.isoformat() if sync_status and sync_status.last_success_at else None,
                "source_count": sync_status.source_count if sync_status else 0,
                "chunk_count": sync_status.chunk_count if sync_status else 0,
                "last_error": sync_status.last_error if sync_status else "Sync henüz çalıştırılmadı.",
            },
        },
        status=200 if healthy else 503,
    )
