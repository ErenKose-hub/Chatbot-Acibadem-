import requests
import PyPDF2
import os
from bs4 import BeautifulSoup
from django.shortcuts import render
from django.http import JsonResponse
from .models import UniversityPDF, UniversityLink


#  YARDIMCI FONKSİYON: Hibrit Veri Toplayıcı ---
def get_hybrid_context():
    context_text = ""

    # Veritabanındaki PDF'leri Okur
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

    #  Link Scrapping
    urls = ["https://www.acibadem.edu.tr/duyurular"]
    for url in urls:
        try:
            res = requests.get(url, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")
            for s in soup(["script", "style", "nav", "footer"]):
                s.decompose()

            context_text += f"\n--- GÜNCEL SİTE VERİSİ ({url}) ---\n"
            context_text += soup.get_text(separator=" ", strip=True)[:1000]
        except Exception as e:
            print(f"Link Kazıma Hatası ({url}): {e}")

    return context_text[:3000]


def chat_home(request):
    # Konusma sirasinda kisa vadeli hafiza
    if "chat_history" not in request.session:
        request.session["chat_history"] = []

    if request.method == "POST":
        user_text = request.POST.get("message")
        history = request.session["chat_history"]
    if request.method == "POST":
        user_text = request.POST.get("message").lower().strip()

        # --- AKILLI FİLTRE: Basit şeyler için kütüphaneye gitme! ---
        easy_words = ["selam", "merhaba", "sa", "slm", "naber", "nasılsın", "hey"]

        if any(word == user_text for word in easy_words) or len(user_text) < 5:
            fresh_context = "Kullanıcı sadece selam verdi veya hal hatır sordu. Okul bilgisini kullanmana gerek yok,  bir karşılama yap."
        else:
            fresh_context = get_hybrid_context()

        # Geçmiş Konuşmayı Metne Dök (Son 3 mesaj yeterli)
        past_convo = ""
        for chat in history[-3:]:
            past_convo += f"Kullanıcı: {chat['user']}\nAsistan: {chat['bot']}\n"

        # Llama Promptlar
        system_instructions = (
            "### SİSTEM TALİMATI ###\n"
            "Sen Acıbadem Üniversitesi'nin resmi asistanısın. Sadece TÜRKÇE cevap ver.\n"
            "akademik , yardımsever ve profesyonel ol. Cevaplarını aşağıdaki bilgilere dayandır.\n\n"
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
                        "temperature": 0.3,
                        "num_predict": 350,
                    },
                },
                timeout=90,
            )
            data = response.json()
            bot_response = data.get("response", "Cevap üretilemedi.").strip()

            history.append({"user": user_text, "bot": bot_response})
            request.session["chat_history"] = history
            request.session.modified = True

            return JsonResponse({"response": bot_response})

        except Exception as e:
            print(f"Hata: {e}")
            return JsonResponse(
                {"response": "Bağlantı koptu , Ollama konteynerini kontrol et."}
            )

    return render(request, "chat/index.html")
