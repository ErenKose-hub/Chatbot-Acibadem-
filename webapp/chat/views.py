import requests
import json
import os
import re

from django.shortcuts import render
from django.http import JsonResponse
from .models import ChatMessage
from .vector_store import semantic_search

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://llm-service:11434")

# Kritik akademik anahtar kelimeler (normalize edilmiş hâlleri)
PRIORITY_KEYWORDS = [
    "kontenjan", "puan", "ucret", "burs", "siralam",
    "muhendislik", "tip", "eczacilik",
]


# ---------------------------------------------------------------------------
# Yardımcı Fonksiyonlar
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Türkçe karakterleri normalize eder; karşılaştırmalarda kullanılır."""
    text = text.lower()
    for src, dst in [("ı", "i"), ("ü", "u"), ("ö", "o"), ("ş", "s"), ("ç", "c"), ("ğ", "g")]:
        text = text.replace(src, dst)
    return text


def has_priority_keyword(normalized_text: str) -> bool:
    """Mesajda kritik akademik kelimelerden biri var mı kontrol eder."""
    return any(kw in normalized_text for kw in PRIORITY_KEYWORDS)


def clean_raw_text(text: str) -> str:
    """
    Veritabanından / ChromaDB'den gelen ham metindeki Markdown tablo gürültüsünü ve
    navigasyon kalıntılarını temizler.
    """
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[-]{3,}", "", text)
    text = re.sub(r":?---+:?", "", text)

    noise_patterns = [
        r"BademNet", r"OBS", r"Kütüphane", r"E-Posta", r"Webmail",
        r"Ana Sayfa", r"İletişim", r"Hızlı Erişim", r"Menü", r"Arama\.\.\.",
        r"Copyright", r"Tüm hakları saklıdır",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def clean_bot_response(text: str) -> str:
    """
    Botun ürettiği yanıttaki Markdown tablo karakterlerini temizler.
    | --- | gibi kalıpları düz metne dönüştürür.
    """
    text = re.sub(r"\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[-]{3,}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def extract_relevant_chunks(text: str, search_words: list) -> str:
    """Tablo verilerini (KV formatı) filtreler; sadece sorguyla eşleşen blokları döndürür."""
    if "--- KAYIT ---" not in text:
        return text

    chunks = text.split("--- KAYIT ---")
    relevant_chunks = [chunks[0][:500]]
    search_keywords = [w.lower() for w in search_words]

    for chunk in chunks[1:]:
        if any(kw in chunk.lower() for kw in search_keywords):
            relevant_chunks.append(chunk.strip())

    if len(relevant_chunks) == 1:
        relevant_chunks.extend([c.strip() for c in chunks[1:4]])

    return "\n--- KAYIT ---\n".join(relevant_chunks)


def rerank_docs(results: list[dict], user_text: str) -> list[dict]:
    """
    5 ChromaDB sonucunu kullanıcı sorgusundaki anahtar kelimelerle skorlar
    ve örtüşme sayısına göre azalan sırada döndürür (en alakalı önce).
    """
    query_words = set(normalize_text(user_text).split())
    scored = []
    for item in results:
        doc_normalized = normalize_text(item["text"])
        score = sum(1 for w in query_words if w in doc_normalized)
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


def build_context(user_text: str, n_results: int = 5) -> tuple[str, list[str]]:
    """
    Kullanıcı sorusuna göre ChromaDB'den anlamsal olarak en yakın belgeleri getirir,
    ardından Dinamik Bölüm Filtreleme ve Cross-Check uygular.
    """
    try:
        results = semantic_search(user_text, n_results=n_results)
    except Exception as e:
        print(f"[ChromaDB Arama Hatası] {e}")
        return "", []

    if not results:
        return "", []

    # --- DİNAMİK BÖLÜM TESPİTİ VE FİLTRELEME ---
    normalized_query = normalize_text(user_text)
    # Sistemdeki bilinen tüm ana bölümler (N-Gram mantığı için genişletilebilir)
    all_departments = [
        "tip", "muhendislik", "eczacilik", "fizyoterapi", "beslenme", "hemsirelik", 
        "psikoloji", "isletme", "iktisat", "hukuk", "gastronomi", "mimarlik"
    ]
    
    # Kullanıcının hangi bölümü sorduğunu tespit et
    active_depts = [dept for dept in all_departments if dept in normalized_query]

    strict_filtered = []
    for item in results:
        doc_text_norm = normalize_text(item["text"])
        source_norm = normalize_text(item["source"])

        # 1. Cross-Check: Eğer kullanıcı spesifik bölümler sorduysa, 
        # dökümanda bu bölümlerden en az biri geçmeli.
        if active_depts:
            if not any(dept in doc_text_norm for dept in active_depts):
                continue
            
            # 2. Negatif Filtre (Tıp sorulunca Duyuru/Beslenme engelleme kuralı devam ediyor)
            if "tip" in active_depts:
                if any(bad in source_norm for bad in ["beslenme", "diyetetik", "duyurular"]):
                    continue

        strict_filtered.append(item)

    if not strict_filtered:
        return "", []

    # Keyword re-ranking
    results = rerank_docs(strict_filtered, user_text)

    words = [w for w in user_text.split() if len(w) > 2]
    parts = []
    sources = []
    for item in results:
        clean = clean_raw_text(item["text"])
        clean = extract_relevant_chunks(clean, words)
        if len(clean) > 100:
            parts.append(clean[:3000])
            sources.append(item["source"])

    context_text = "\n--- SAYFA AYRACI ---\n".join(parts)
    return context_text, list(set(sources))


# ---------------------------------------------------------------------------
# View: Ana Sohbet (chat_home)
# ---------------------------------------------------------------------------

def chat_home(request):
    """Ana sohbet arayüzünü yöneten view."""
    if request.method == "GET":
        request.session["chat_history"] = []
    elif "chat_history" not in request.session:
        request.session["chat_history"] = []

    if request.method == "POST":
        user_text = request.POST.get("message", "").strip()
        normalized = normalize_text(user_text)

        # --- 1. KÜÇÜK SOHBET KONTROLÜ ---
        chitchat_words = [
            "selam", "merhaba", "nasilsin", "naber", "hey",
            "merhabalar", "selamlar", "sa", "slm",
        ]
        if normalized in chitchat_words or len(user_text) < 3:
            bot_response = (
                "Merhaba! Ben Acıbadem Üniversitesi Akademik Asistanıyım. "
                "Size üniversitemiz, akademik programlar veya kontenjanlar "
                "hakkında bilgi verebilirim. Ne öğrenmek istersiniz?"
            )
            return JsonResponse({"response": bot_response})

        # --- 2. VERİTABANI SORGUSU (ChromaDB Semantic RAG) ---
        fresh_context, sources = build_context(user_text)

        # SIKI RED: Eğer context boşsa veya bölüm eşleşmediyse doğrudan reddet
        if not fresh_context:
            refusal_msg = (
                "Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde güncel bir veri bulunmamaktadır. "
                "Lütfen aday öğrenci sayfasını (aday.acibadem.edu.tr) ziyaret edin."
            )
            return JsonResponse({"response": refusal_msg})

        # --- 3. SYSTEM PROMPT ---
        history = request.session["chat_history"]

        # Geçmişi son 3 mesajla sınırla
        past_convo = ""
        for chat in history[-3:]:
            past_convo += f"Kullanıcı: {chat['user']}\nAsistan: {chat['bot']}\n"

        # Akıllı context önceliği notu
        context_note = (
            "[ÖNEMLİ: Aşağıdaki KAYNAK METİN veritabanından yeni çekilmiştir ve "
            "konuşma geçmişinden DAHA ÖNCE gelir. Cevabını mutlaka bu kaynağa dayandır.]\n"
            if fresh_context and "bulunamadı" not in fresh_context
            else ""
        )

        system_instructions = (
            "Sen Acıbadem Üniversitesi'nin resmi akademik asistanısın. "
            "Görevin, [KAYNAK METİN] içindeki bilgileri kullanarak soruları yanıtlamaktır.\n\n"

            "KESİN KURALLAR:\n"
            "- Cevaplarında asla '[KAYNAK METİN]', 'Context', 'Sistem promptu' veya 'Veritabanı' gibi teknik terimlerden bahsetme. Bilgiyi doğrudan ve doğal bir dille aktar.\n"
            "- Ham metin içindeki 'tıklayınız', 'indir', 'PDF' gibi web komutlarını tamamen temizle.\n"
            "- Eğer [KAYNAK METİN] içinde kullanıcının sorduğu spesifik bölüm veya konu hakkında KESİN bir bilgi yoksa, ASLA yorum yapma veya uydurma.\n"
            "- Bilgi bulunamadığında SADECE şu cümleyi söyle: 'Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde güncel bir veri bulunmamaktadır. Lütfen aday öğrenci sayfasını ziyaret edin.'\n"
            "- Giriş cümleleri (Örn: 'Verilere göre...') kullanmadan direkt konuya gir.\n"
            "- Sadece Türkçe konuş.\n\n"
            f"{context_note}\n"
            f"[KAYNAK METİN BAŞLANGICI]\n{fresh_context[:6000]}\n[KAYNAK METİN BİTİŞİ]"
        )

        

        messages = []
        if past_convo:
            messages.append({"role": "user", "content": f"Önceki konuşmamız özeti:\n{past_convo}"})
            messages.append({"role": "assistant", "content": "Anladım, önceki konuşmalarımızı hatırlayarak net cevaplar vereceğim."})
        messages.append({"role": "user", "content": user_text})

        # --- 4. OLLAMA İSTEĞİ ---
        try:
            res = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": "gemma:2b",
                    "messages": [{"role": "system", "content": system_instructions}] + messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_ctx": 8192,
                        "num_predict": 300,
                    },
                },
                timeout=180,
            )
            res_json = res.json()
            bot_response = res_json.get("message", {}).get(
                "content", "Üzgünüm, şu an yanıt veremiyorum."
            ).strip()
            bot_response = clean_bot_response(bot_response)

            # Kaynakları terminale yaz ve bot cevabına ekle
            if sources:
                source_note = "\n\n(Kaynak: " + ", ".join(sources) + ")"
                print(f"[RAG] Kullanılan Kaynaklar: {sources}")
                bot_response += source_note

            history.append({"user": user_text, "bot": bot_response})
            request.session["chat_history"] = history
            request.session.modified = True

            ChatMessage.objects.create(user_message=user_text, bot_response=bot_response)

        except Exception:
            bot_response = "Şu an sistemimde bir yoğunluk var, lütfen biraz bekleyip tekrar sorunuz."

        return JsonResponse({"response": bot_response})

    return render(request, "chat/index.html")


# ---------------------------------------------------------------------------
# View: Harici API (chat_api) — Hibrit Filtreleme + ChromaDB
# ---------------------------------------------------------------------------

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

    normalized = normalize_text(user_text)
    word_count = len(user_text.split())

    # --- HİBRİT KARAR MEKANİZMASI ---
    if has_priority_keyword(normalized) or word_count >= 3:
        # ChromaDB'ye git
        fresh_context, sources = build_context(user_text)
        if not fresh_context:
            return JsonResponse({
                "response": "Üzgünüm, aradığınız bölüm (veya konu) hakkında sistemimde güncel bir veri bulunmamaktadır. Lütfen aday öğrenci sayfasını ziyaret edin."
            })
    else:
        # Kısa mesaj → Small Talk modu
        return JsonResponse({
            "response": "Merhaba! Acıbadem Üniversitesi hakkında ne öğrenmek istersiniz? Kontenjan ve puanlar için bölüm adı belirterek sorabilirsiniz."
        })

    # --- SYSTEM PROMPT ---
    system_prompt = (
        "Sen Acıbadem Üniversitesi'nin resmi akademik asistanısın. "
        "Kaynak metinde bilgi yoksa asla uydurma ve 'Üzgünüm, aradığınız bölüm hakkında güncel veri bulunmamaktadır' de. "
        "Cevaplarında '[KAYNAK METİN]' veya 'Sistem promptu' gibi terimler kullanma. Akıcı bir Türkçe ile doğrudan cevap ver."
    )

    full_prompt = (
        f"{system_prompt}\n\n"
        f"KAYNAK VERİ:\n{fresh_context[:2000]}\n\n"
        f"Kullanıcı Sorusu: {user_text}\nAsistan Yanıtı:"
    )

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": "gemma:2b",
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 300},
            },
            timeout=120,
        )
        bot_response = response.json().get("response", "Üzgünüm, yanıt veremiyorum.").strip()
        bot_response = clean_bot_response(bot_response)
        
        # Kaynakları bot cevabına ekle
        if sources:
            source_note = "\n\n(Kaynak: " + ", ".join(sources) + ")"
            print(f"[RAG API] Kullanılan Kaynaklar: {sources}")
            bot_response += source_note

        ChatMessage.objects.create(user_message=user_text, bot_response=bot_response)
    except Exception:
        bot_response = "Bağlantı hatası oluştu."

    return JsonResponse({"response": bot_response})