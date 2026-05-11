"""
direct_answer.py — LLM'e gitmeden anında yanıt veren kural tabanlı modül.

Basit, sık tekrar eden sorular için önceden tanımlı yanıtlar içerir.
check_direct_answer(user_text) → str | None döndürür:
  - str  : eşleşme bulundu, bu yanıtı kullan (LLM'e gitme)
  - None : eşleşme yok, normal RAG akışına devam et
"""

from __future__ import annotations
import re

# ─── Yanıt Şablonları ────────────────────────────────────────────────────────

_GREETING = (
    "Merhaba! Ben Acıbadem Üniversitesi Akademik Asistanıyım. "
    "Üniversitemiz, akademik programlar, bölümler veya kontenjanlar "
    "hakkında sorularınızı yanıtlayabilirim. Ne öğrenmek istersiniz?"
)

_ADDRESS = (
    "Acıbadem Üniversitesi ana kampüsü Kerem Ali Paşa Cad. No:32 "
    "Ataşehir / İstanbul adresinde bulunmaktadır. "
    "Kampüs hakkında detaylı bilgi için acibadem.edu.tr adresini ziyaret edebilirsiniz."
)

_CONTACT = (
    "Acıbadem Üniversitesi'ne 0216 500 44 44 numaralı telefon veya "
    "info@acibadem.edu.tr e-posta adresiyle ulaşabilirsiniz. "
    "Aday öğrenciler için aday.acibadem.edu.tr sayfasını incelemenizi öneririz."
)

_WHO_ARE_YOU = (
    "Ben Acıbadem Üniversitesi'nin resmi Akademik Asistanıyım. "
    "Bölümler, kontenjanlar, puanlar ve kampüs hakkında sorularınızı yanıtlamak için buradayım."
)

_THANKS = (
    "Rica ederim! Başka bir sorunuz olursa yardımcı olmaktan memnuniyet duyarım."
)

# ─── Kural Tablosu ───────────────────────────────────────────────────────────
# (normalize edilmiş tetikleyici kelimeler listesi, karşılık gelen yanıt)

_RULES: list[tuple[list[str], str]] = [
    # Selamlaşma
    (
        ["selam", "merhaba", "mrb", "slm", "merhabalar", "selamlar", "hey", "sa", "naber", "nasilsin"],
        _GREETING,
    ),
    # Adres / Konum
    (
        ["adres", "nerede", "konum", "kampus", "lokasyon", "ulasim", "nasil gidilir"],
        _ADDRESS,
    ),
    # İletişim
    (
        ["iletisim", "telefon", "mail", "eposta", "e-posta", "numara", "irtibat"],
        _CONTACT,
    ),
    # Kim olduğu
    (
        ["kimsin", "sen kimsin", "nedir bu", "ne yapiyorsun", "asistan"],
        _WHO_ARE_YOU,
    ),
    # Teşekkür
    (
        ["tesekkur", "sagol", "eyvallah", "tsk", "ty", "thx"],
        _THANKS,
    ),
]


def _normalize(text: str) -> str:
    """Türkçe karakterleri normalize eder ve küçük harfe çevirir."""
    text = text.lower()
    for src, dst in [("ı", "i"), ("ü", "u"), ("ö", "o"), ("ş", "s"), ("ç", "c"), ("ğ", "g")]:
        text = text.replace(src, dst)
    return text


def check_direct_answer(user_text: str) -> str | None:
    """
    Kullanıcı metninin bilinen basit soru kalıplarından biriyle eşleşip
    eşleşmediğini kontrol eder.

    Args:
        user_text: Ham kullanıcı metni.

    Returns:
        Eşleşme varsa hazır yanıt metni, yoksa None.
    """
    normalized = _normalize(user_text.strip())

    # Çok kısa mesajlar (1 karakter) → selamlama olarak kabul et
    if len(normalized) <= 1:
        return _GREETING

    word_count = len(normalized.split())

    # Sadece tam kelime eşleşmeleri (word boundaries)
    for triggers, answer in _RULES:
        for trigger in triggers:
            if re.search(rf"\b{re.escape(trigger)}\b", normalized):
                # Eğer selamlama ise ve cümle uzunsa (örn: "merhaba tıp kontenjanı") LLM'e gitsin
                if answer == _GREETING and word_count > 3:
                    continue
                return answer

    return None
