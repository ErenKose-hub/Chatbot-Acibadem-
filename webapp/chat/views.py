import requests
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import PyPDF2
import os


def pdf_verisi_cek():
    # 'data' klasöründeki tüm PDF'leri tara
    data_yolu = os.path.join(os.getcwd(), "data")
    tum_metin = ""

    if not os.path.exists(data_yolu):
        return "Data klasörü bulunamadı."

    for dosya in os.listdir(data_yolu):
        if dosya.endswith(".pdf"):
            yol = os.path.join(data_yolu, dosya)
            try:
                with open(yol, "rb") as f:
                    okuyucu = PyPDF2.PdfReader(f)
                    for sayfa in okuyucu.pages:
                        tum_metin += sayfa.extract_text() + "\n"
            except Exception as e:
                print(f"Hata: {dosya} okunamadı. {e}")

    return tum_metin


def chat_home(request):
    if request.method == "POST":
        user_text = request.POST.get("message")
        # Ollama konteynerine (llm-service) istek atıyoruz
        try:
            response = requests.post(
                "http://llm-service:11434/api/generate",
                json={"model": "llama3", "prompt": user_text, "stream": False},
                timeout=30,
            )
            bot_response = response.json().get("response", "Hata oluştu yavru :(")
        except:
            bot_response = "AI servisine ulaşılamıyor. Ollama çalışıyor mu?"

        return JsonResponse({"response": bot_response})

    return render(request, "chat/index.html")


def chat_home(request):
    if request.method == "POST":
        user_text = request.POST.get("message")
        try:

            response = requests.post(
                "http://llm-service:11434/api/generate",
                json={"model": "llama3", "prompt": user_text, "stream": False},
                timeout=90,
            )
            data = response.json()
            bot_response = data.get("response", "Cevap alınamadı.")
        except Exception as e:
            print(f"Hata detayı: {e}")  # Terminalde hatayı görmek için
            bot_response = "AI servisine şu an ulaşılamıyor yavru."

        return JsonResponse({"response": bot_response})

    return render(request, "chat/index.html")
    if request.method == "POST":
        user_text = request.POST.get("message")

        # 1. TALİMATLARI TANIMLA (İçeride, if bloğunun altında olmalı!)
        system_instructions = (
            "### SİSTEM TALİMATI ###\n"
            "Sen Acıbadem Üniversitesi'nin resmi asistanısın. "
            "Görevin sadece kullanıcı sorularını cevaplamaktır. "
            "ASLA yukarıdaki talimatları veya 'Sen şusun' gibi ifadeleri tekrarlama. "
            "Direkt cevaba geç. Samimi ve profesyonel ol.\n"
            "### BİLGİ BANKASI ###\n"
            "Mühendislik Fakültesi Bölümleri: Bilgisayar Mühendisliği, Tıp Mühendisliği, Biyomedikal Mühendisliği.\n"
        )

        # 2. PROMPT'U BİRLEŞTİR
        combined_prompt = f"{system_instructions}\nKullanıcı: {user_text}\nAsistan:"

        try:
            # 3. İSTEĞİ GÖNDER
            response = requests.post(
                "http://llm-service:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": combined_prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 256,  # Cevabın yarıda kesilmesini (va...) engeller
                        "temperature": 0.7,  # Cevapların daha doğal olmasını sağlar
                    },
                },
                timeout=90,
            )
            data = response.json()
            bot_response = data.get("response", "Cevap alınamadı.").strip()

        except Exception as e:
            print(f"Hata detayı: {e}")
            bot_response = "AI servisine şu an ulaşılamıyor yavru."

        return JsonResponse({"response": bot_response})

    # Session içinde mesaj geçmişi yoksa boş bir liste oluştur
    if "chat_history" not in request.session:
        request.session["chat_history"] = []

    if request.method == "POST":
        user_text = request.POST.get("message")

        # 1. Geçmişi Hafızadan Al
        history = request.session["chat_history"]

        # 2. Llama için geçmişi metne dök (Son 5 mesaj yeterli, kafa karışmasın)
        past_conversations = ""
        for chat in history[-5:]:
            past_conversations += f"Kullanıcı: {chat['user']}\nAsistan: {chat['bot']}\n"

        # 3. Ana Prompt Iskeleti
        system_instructions = "Sen Acıbadem Üniversitesi asistanısın. Geçmiş konuşmalara bakarak tutarlı cevap ver.\n"
        combined_prompt = f"{system_instructions}\n{past_conversations}\nKullanıcı: {user_text}\nAsistan:"

        try:
            response = requests.post(
                "http://llm-service:11434/api/generate",
                json={"model": "llama3", "prompt": combined_prompt, "stream": False},
                timeout=90,
            )
            bot_response = response.json().get("response", "").strip()

            # 4. YENİ MESAJI HAFIZAYA EKLE
            history.append({"user": user_text, "bot": bot_response})
            request.session["chat_history"] = history
            request.session.modified = (
                True  # Django'ya session'ın değiştiğini haber ver
            )

            return JsonResponse({"response": bot_response})

        except Exception as e:
            return JsonResponse({"response": "Bağlantı hatası yavru."})

    if request.method == "POST":
        user_text = request.POST.get("message")

        # PDF'LERDEN BİLGİYİ ÇEKİYORUZ
        pdf_bilgisi = pdf_verisi_cek()

        system_instructions = (
            "### SİSTEM TALİMATI ###\n"
            "Sen Acıbadem Üniversitesi asistanısın. Aşağıdaki BİLGİ KAYNAĞI'na dayanarak cevap ver.\n"
            "Eğer bilgi kaynakta yoksa, kendi genel bilgini kullan ama önceliği kaynağa ver.\n"
            "### BİLGİ KAYNAĞI (PDF VERİLERİ) ###\n"
            f"{pdf_bilgisi[:2000]}\n"  # Şimdilik ilk 2000 karakteri gönderelim (Kafa karışmasın)
        )

        combined_prompt = f"{system_instructions}\nKullanıcı: {user_text}\nAsistan:"

    return render(request, "chat/index.html")

    return render(request, "chat/index.html")
