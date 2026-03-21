import requests
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


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
