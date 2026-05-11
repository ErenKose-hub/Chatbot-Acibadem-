"""
prompt_manager.py — Sistem prompt'ları ve bot yanıt temizleme.

Bu modül:
  - build_system_prompt()  : chat_home için zengin sistem talimatları
  - build_api_prompt()     : chat_api için sade generate prompt'u
  - clean_bot_response()   : LLM çıktısındaki Markdown tablo gürültüsünü temizler
"""

from __future__ import annotations
import re


# ─── Bot Yanıt Temizleme ─────────────────────────────────────────────────────

def clean_bot_response(text: str) -> str:
    """
    LLM'in ürettiği yanıttaki Markdown tablo karakterlerini temizler.
    | --- | gibi kalıpları düz metne dönüştürür.
    """
    text = re.sub(r"\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[-]{3,}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# ─── Sistem Prompt'u (chat_home — /api/chat) ─────────────────────────────────

def build_system_prompt(fresh_context: str) -> str:
    """
    chat_home için tam sistem promptu oluşturur.

    Args:
        fresh_context: ChromaDB'den gelen bağlam metni (zaten 6000 karakter
                       sınırıyla build_context tarafından sağlanmalıdır).

    Returns:
        LLM'e gönderilecek sistem talimatı metni.
    """
    return (
        "Sen Acıbadem Üniversitesi'nin resmi asistanısın. Asla kendini tanıtma veya selamlama yapma (Örn: 'Merhaba, ben asistanım' DEME).\n\n"
        "Sana verilen [KAYNAK METİN] içindeki bilgileri kullanarak soruları yanıtla.\n"
        "Kullanıcı spesifik bir soru sorarsa (kontenjan, ücret vb.) sadece o spesifik veriyi kısa ve net bir şekilde ver.\n"
        "Kullanıcı genel bir bilgi isterse ('Üniversite hakkında bilgi ver' gibi), kaynak metindeki bilgileri kısaca özetle.\n"
        "Eğer kaynak metinde soruyla ilgili HİÇBİR BİLGİ YOKSA, kendi genel bilginle yanıtlamaya çalış. "
        "Yine de emin değilsen 'Bu konuda sistemimde güncel bilgi bulunmamaktadır' de.\n\n"
        "Gereksiz nezaket cümlelerini tamamen bırak, direkt cevaba odaklan.\n\n"
        f"[KAYNAK METİN BAŞLANGICI]\n{fresh_context[:6000]}\n[KAYNAK METİN BİTİŞİ]"
    )


# ─── API Prompt'u (chat_api — /api/generate) ─────────────────────────────────

def build_api_prompt(fresh_context: str, user_text: str) -> str:
    """
    chat_api için sade generate prompt'u oluşturur.

    Args:
        fresh_context: ChromaDB'den gelen bağlam metni.
        user_text: Kullanıcının sorusu.

    Returns:
        /api/generate endpoint'ine gönderilecek tam prompt.
    """
    system = (
        "Sen Acıbadem Üniversitesi bilgi sistemisin. Sana verilen [KAYNAK VERİ] içindeki bilgileri kullanarak kısa ve net cevaplar ver.\n\n"
        "Eğer kaynakta rakam varsa (kontenjan, ücret vb.) direkt o rakamı söyle.\n\n"
        "Kaynakta bilgi yoksa \"Bu konuda sistemimde güncel bilgi bulunmamaktadır\" de.\n\n"
        "Gereksiz nezaket cümlelerini bırak, direkt cevaba odaklan."
    )

    return (
        f"{system}\n\n"
        f"KAYNAK VERİ:\n{fresh_context[:2000]}\n\n"
        f"Kullanıcı Sorusu: {user_text}\nAsistan Yanıtı:"
    )
