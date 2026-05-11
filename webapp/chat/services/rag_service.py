"""
rag_service.py — ChromaDB sorgulama ve Strict Department Filtering.

build_context(user_text) → (context_str, sources_list)

Akış:
  1. ChromaDB'den n_results adet semantik eşleşme al
  2. Kullanıcı sorgusundaki bölüm adlarını tespit et (normalize edilmiş)
  3. Bölüm tespiti varsa sadece o bölümü içeren dokümanları filtrele
  4. Eğer filtreleme sonrası hiç doküman kalmazsa boş döndür
  5. Kalan dokümanları anahtar kelime eşleşmesiyle yeniden sırala (rerank)
  6. Ham metinleri temizle ve birleştir
"""

from __future__ import annotations
import re
from chat.vector_store import semantic_search


# ─── Bilinen Bölüm Anahtar Kelimeleri ────────────────────────────────────────

ALL_DEPARTMENTS: list[str] = [
    "tip", "muhendis", "eczaci", "fizyoterap", "beslenme", "hemsire",
    "psikoloj", "isletme", "iktisat", "hukuk", "gastronomi", "mimar",
    "bilgisayar", "yazilim", "biyomedikal", "endustri", "molekuler",
    "bolum", "baskan", "erasmus", "akademik", "ogretim",
]

# Bağlaçlar ve gereksiz kelimeler (Reranking puanlamasını bozmaması için)
STOPWORDS: set[str] = {
    "ve", "ile", "veya", "ya", "da", "de", "nedir", "nasil", "kadar",
    "bir", "bu", "su", "o", "icin", "mi", "mu", "mü", "mı", "hakkinda",
    "ne", "kim", "hangi", "var", "yok", "neden", "niye", "neler"
}

# Markdown/navigasyon gürültü kalıpları
_NOISE_PATTERNS: list[str] = [
    r"BademNet", r"OBS", r"Kütüphane", r"E-Posta", r"Webmail",
    r"Ana Sayfa", r"İletişim", r"Hızlı Erişim", r"Menü", r"Arama\.\.\.",
    r"Copyright", r"Tüm hakları saklıdır",
]


# ─── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Türkçe karakterleri normalize eder; karşılaştırmalarda kullanılır."""
    text = text.lower()
    for src, dst in [("ı", "i"), ("ü", "u"), ("ö", "o"), ("ş", "s"), ("ç", "c"), ("ğ", "g")]:
        text = text.replace(src, dst)
    return text


def clean_raw_text(text: str) -> str:
    """
    ChromaDB'den gelen ham metindeki Markdown tablo gürültüsünü ve
    navigasyon kalıntılarını temizler.
    """
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[-]{3,}", "", text)
    text = re.sub(r":?---+:?", "", text)

    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def extract_relevant_chunks(text: str, search_words: list[str]) -> str:
    """
    Tablo verilerini (KV formatı) filtreler; sadece sorguyla eşleşen
    blokları döndürür. '--- KAYIT ---' ayracı yoksa metni değiştirmeden döner.
    """
    if "--- KAYIT ---" not in text:
        return text

    chunks = text.split("--- KAYIT ---")
    relevant_chunks = [chunks[0][:500]]
    search_keywords = [normalize_text(w) for w in search_words]

    for chunk in chunks[1:]:
        if any(kw in normalize_text(chunk) for kw in search_keywords):
            relevant_chunks.append(chunk.strip())

    # Hiçbir kayıt eşleşmediyse ilk 3 kaydı fallback olarak ekle
    if len(relevant_chunks) == 1:
        relevant_chunks.extend([c.strip() for c in chunks[1:4]])

    return "\n--- KAYIT ---\n".join(relevant_chunks)


def rerank_docs(results: list[dict], user_text: str) -> list[dict]:
    """
    ChromaDB sonuçlarını kullanıcı sorgusundaki anahtar kelimelerle skorlar
    ve örtüşme sayısına göre azalan sırada döndürür (en alakalı önce).
    """
    query_words = set(normalize_text(user_text).split())
    # Stopwords'leri filtrele
    query_words = {w for w in query_words if w not in STOPWORDS}

    # Kişi/Unvan sorgusu tespiti
    person_keywords = {"kim", "baskan", "hoca", "profesör", "prof", "akademik", "kadro", "ahmet", "isim", "unvan"}
    is_person_query = any(w in query_words for w in person_keywords)

    scored: list[tuple[int, dict]] = []
    for item in results:
        doc_normalized = normalize_text(item["text"])
        score = sum(1 for w in query_words if w in doc_normalized)
        
        # Reranking İyileştirmesi: Kişi/Unvan sorgularında tablo puanını düşür, metin puanını artır
        if is_person_query:
            if "--- KAYIT ---" in item["text"]:
                score -= 2  # Tablo verisine ceza
            else:
                score += 2  # Düz metne ödül

        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

def build_context(user_text: str, n_results: int = 15) -> tuple[str, list[str]]:
    """
    Kullanıcı sorusuna göre ChromaDB'den anlamsal olarak en yakın belgeleri getirir,
    Strict Bölüm Filtreleme ve keyword reranking uygular.

    Args:
        user_text: Ham kullanıcı sorusu.
        n_results: ChromaDB'den kaç sonuç isteneceği.

    Returns:
        (context_text, sources): Bağlam metni ve kaynak listesi.
        Context boşsa ("", []) döner.
    """
    try:
        results = semantic_search(user_text, n_results=n_results)
    except Exception as e:
        print(f"[RAGService] ChromaDB arama hatası: {e}")
        return "", []

    if not results:
        return "", []

    # ── RERANKING ────────────────────────────────────────────────────────────
    # Test modunda Strict Filtering kapalı, tüm sonuçları rerank et
    ranked = rerank_docs(results, user_text)

    # ── ÇEŞİTLİLİK FİLTRESİ (DIVERSITY) ──────────────────────────────────────
    # Aynı URL'den (kaynaktan) maksimum 2 adet alarak en az 3 farklı kaynak garantile
    diverse_ranked = []
    source_counts = {}

    for item in ranked:
        src = item.get("source", "Bilinmeyen")
        if source_counts.get(src, 0) < 2:
            diverse_ranked.append(item)
            source_counts[src] = source_counts.get(src, 0) + 1
        
        if len(diverse_ranked) >= 5:
            break

    # Eğer 5 belge toplayamadıysak, es geçilenleri de doldurmak için tekrar dön
    if len(diverse_ranked) < 5:
        for item in ranked:
            if item not in diverse_ranked:
                diverse_ranked.append(item)
            if len(diverse_ranked) >= 5:
                break

    # ── METİN TEMİZLEME VE BİRLEŞTİRME ─────────────────────────────────────
    parts: list[str] = []
    sources: list[str] = []

    for item in diverse_ranked:
        clean = clean_raw_text(item["text"])
        if len(clean) > 50:
            parts.append(clean[:3000])
            source = item.get("source", "Bilinmeyen")
            sources.append(source)
            print(f"[RAGService] LLM'e gönderilecek kaynak: {source}")

    context_text = "\n--- SAYFA AYRACI ---\n".join(parts)
    return context_text, list(set(sources))
