import requests
import PyPDF2
import os
from bs4 import BeautifulSoup
from django.shortcuts import render
from django.http import JsonResponse
from .models import UniversityPDF, UniversityLink


# --- 1. YARDIMCI FONKSİYON: Hibrit Veri Toplayıcı ---
def get_hybrid_context():
    context_text = ""

    # BÖLÜM A: Veritabanındaki PDF'leri Oku
    pdf_docs = UniversityPDF.objects.all()
    for doc in pdf_docs:
        try:
            if os.path.exists(doc.file.path):
                with open(doc.file.path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        context_text += page.extract_text() + "\n"
        except Exception as e:
            print(f"PDF Okuma Hatası ({doc.title}): {e}")

    # BÖLÜM B: Canlı Linkleri Kazı (Scraping)
    urls = [
        "https://www.acibadem.edu.tr/duyurular"
    ]  # Burayı istersen modele de bağlayabiliriz sonra
    for url in urls:
        try:
            res = requests.get(url, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")
            # Gereksizleri temizle
            for s in soup(["script", "style", "nav", "footer"]):
                s.decompose()

            context_text += f"\n--- GÜNCEL SİTE VERİSİ ({url}) ---\n"
            context_text += soup.get_text(separator=" ", strip=True)[:1000]
        except Exception as e:
            print(f"Link Kazıma Hatası ({url}): {e}")

    return context_text[:3000]  # Llama'nın kafası karışmasın diye sınır


# --- 2. ANA FONKSİYON: Chat Yönetimi ---
def chat_home(request):
    # Session (Hafıza) Başlatma
    if "chat_history" not in request.session:
        request.session["chat_history"] = []

    if request.method == "POST":
        user_text = request.POST.get("message")
        history = request.session["chat_history"]

        # Güncel PDF ve Web bilgisini al
        fresh_context = get_hybrid_context()

        # Geçmiş Konuşmayı Metne Dök (Son 3 mesaj yeterli)
        past_convo = ""
        for chat in history[-3:]:
            past_convo += f"Kullanıcı: {chat['user']}\nAsistan: {chat['bot']}\n"

        # Llama'ya gidecek nihai Prompt
        system_instructions = (
            "### SİSTEM TALİMATI ###\n"
            "Sen Acıbadem Üniversitesi'nin resmi asistanısın. Sadece TÜRKÇE cevap ver.\n"
            "Samimi, yardımsever ve profesyonel ol. Cevaplarını aşağıdaki bilgilere dayandır.\n\n"
            f"### BİLGİ KAYNAĞI (PDF & WEB) ###\n{fresh_context}\n\n"
            "### BİLGİ BANKASI ###\n"
            "Mühendislik Fakültesi: Bilgisayar, Tıp ve Biyomedikal Mühendisliği bölümlerini içerir.\n\n"
        )

        full_prompt = f"{system_instructions}\n### GEÇMİŞ KONUŞMA ###\n{past_convo}\n### YENİ SORU ###\nKullanıcı: {user_text}\nAsistan:"

        try:
            response = requests.post(
                "http://llm-service:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,  # Daha tutarlı cevaplar için düşük sıcaklık
                        "num_predict": 350,  # Cevabın uzunluğu
                    },
                },
                timeout=90,
            )
            data = response.json()
            bot_response = data.get("response", "Cevap üretilemedi.").strip()

            # Hafızayı Güncelle
            history.append({"user": user_text, "bot": bot_response})
            request.session["chat_history"] = history
            request.session.modified = True

            return JsonResponse({"response": bot_response})

        except Exception as e:
            print(f"Hata: {e}")
            return JsonResponse(
                {"response": "Bağlantı koptu bebiş, Ollama konteynerini kontrol et."}
            )

    # GET isteği gelirse sayfayı yükle
    return render(request, "chat/index.html")
