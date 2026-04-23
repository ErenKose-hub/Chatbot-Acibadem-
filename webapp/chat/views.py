import requests
import json
import os
import re

from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from .models import UniversityContent, ChatMessage

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://llm-service:11434")


def normalize_text(text):
    """Türkçe karakterleri normalize eder, selamlama tespitinde kullanılır."""
    text = text.lower()
    for src, dst in [('ı','i'),('ü','u'),('ö','o'),('ş','s'),('ç','c'),('ğ','g')]:
        text = text.replace(src, dst)
    return text


def build_context(user_text, max_results=3, max_chars=700):
    """Kullanıcı sorusuna göre veritabanından alakalı context oluşturur."""
    words = [w for w in user_text.split() if len(w) > 3]

    if not words:
        return None

    # PostgreSQL Full-Text Search ile akıllı arama ve sıralama
    search_query = SearchQuery(" | ".join(words), search_type='raw')
    search_vector = SearchVector("raw_text")

    related_data = (
        UniversityContent.objects.annotate(rank=SearchRank(search_vector, search_query))
        .filter(rank__gte=0.01)  # Belli bir alaka düzeyinin üzerindekileri al
        .order_by("-rank")[:max_results]
    )

    if related_data.exists():
        parts = []
        for item in related_data:
            clean = item.raw_text.strip()
            if len(clean) > 100:  # Çok kısa (menü/başlık) metinleri atla
                parts.append(clean[:max_chars])
        return "\n--- SAYFA AYRACI ---\n".join(parts) if parts else None

    return None


def chat_home(request):
    """Ana sohbet arayüzünü yöneten view."""
    if "chat_history" not in request.session:
        request.session["chat_history"] = []

    if request.method == "POST":
        user_text = request.POST.get("message", "").strip()

        # --- 1. KÜÇÜK SOHBET KONTROLÜ ---
        chitchat_words = ["selam", "merhaba", "nasilsin", "naber", "hey", "merhabalar", "selamlar", "sa", "slm"]
        if normalize_text(user_text) in chitchat_words or len(user_text) < 3:
            bot_response = "Merhaba! Ben Acıbadem Üniversitesi Akademik Asistanıyım. Size üniversitemiz, akademik programlar veya kontenjanlar hakkında bilgi verebilirim. Ne öğrenmek istersiniz?"
            return JsonResponse({"response": bot_response})

        # --- 2. VERİTABANI SORGUSU (RAG) ---
        # Takip soruları (örn: "peki kaç kişi alıyor?") bağlamsız kaldığı için, 
        # arama yaparken bir önceki kullanıcının sorusunu da arama sorgusuna ekliyoruz.
        search_text = user_text
        if len(request.session["chat_history"]) > 0:
            last_user_msg = request.session["chat_history"][-1]["user"]
            search_text = f"{last_user_msg} {user_text}"

        fresh_context = build_context(search_text)

        if fresh_context is None and not any(len(w) > 3 for w in user_text.split()):
            return JsonResponse({"response": "Lütfen üniversite ile ilgili daha açıklayıcı bir soru sorun."})

        if fresh_context is None:
            fresh_context = "Veritabanında bu konuyla ilgili doğrudan bir eşleşme bulunamadı."

        # --- 3. PROMPT ---
        history = request.session["chat_history"]
        past_convo = ""
        for chat in history[-2:]:
            past_convo += f"Kullanıcı: {chat['user']}\nAsistan: {chat['bot']}\n"

        system_instructions = (
            "SEN BİR ÜNİVERSİTE ASİSTANISIN. SADECE VE SADECE SANA VERİLEN METNE GÖRE CEVAP VER.\n\n"
            f"METİN:\n{fresh_context[:1000]}\n\n"
            "DİKKAT:\n"
            "1. Kullanıcı metinde OLMAYAN bir şey sorarsa (örn: bölüm başkanı, kimdir, telefon numarası) KESİNLİKLE uydurma. Sadece 'Bu bilgi sistemimde kayıtlı değil' de.\n"
            "2. Cevabına 'Kurallar 1, 2' gibi teknik yazılar ekleme.\n"
            "3. Doğal, kısa ve yardımcı bir dille konuş."
        )

        full_prompt = (
            f"{system_instructions}\n\nGEÇMİŞ SOHBET:\n{past_convo}\nSoru: {user_text}\nCevap:"
        )

        # --- 4. OLLAMA İSTEĞİ ---
        try:
            res = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": "gemma:2b",
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_ctx": 4096,
                        "num_predict": 200,
                    },
                },
                timeout=60,
            )
            bot_response = res.json().get("response", "Üzgünüm, şu an yanıt veremiyorum.").strip()

            history.append({"user": user_text, "bot": bot_response})
            request.session["chat_history"] = history
            request.session.modified = True

            # Başarılı cevabı veritabanına kaydet
            ChatMessage.objects.create(user_message=user_text, bot_response=bot_response)

        except Exception:
            bot_response = "Şu an sistemimde bir yoğunluk var, lütfen biraz bekleyip tekrar sorunuz."

        return JsonResponse({"response": bot_response})

    return render(request, "chat/index.html")


def chat_api(request):
    """Harici API istemcileri için JSON tabanlı endpoint."""
    if request.method != "POST":
        return JsonResponse({"error": "Sadece POST destekleniyor."}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Geçersiz JSON formatı."}, status=400)

    user_text = data.get("message", "").strip()
    if not user_text:
        return JsonResponse({"error": "Mesaj boş olamaz."}, status=400)

    fresh_context = build_context(user_text) or "Veri bulunamadı."

    full_prompt = (
        "SEN ACIBADEM ÜNİVERSİTESİ AKADEMİK ASİSTANISIN.\n"
        "SADECE SANA VERİLEN KAYNAK VERİYİ KULLAN. KENDİNDEN BİLGİ EKLEME.\n"
        "METİNDE CEVAP YOKSA 'VERİTABANIMDA BU BİLGİYE RASTLAYAMADIM' DE.\n\n"
        f"KAYNAK VERİ:\n{fresh_context[:1000]}\n\n"
        f"Kullanıcı Sorusu: {user_text}\nAsistan Yanıtı:"
    )

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": "gemma:2b",
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 200},
            },
            timeout=60,
        )
        bot_response = response.json().get("response", "Üzgünüm, yanıt veremiyorum.").strip()
        # Başarılı cevabı veritabanına kaydet
        ChatMessage.objects.create(user_message=user_text, bot_response=bot_response)
    except Exception:
        bot_response = "Bağlantı hatası oluştu."

    return JsonResponse({"response": bot_response})