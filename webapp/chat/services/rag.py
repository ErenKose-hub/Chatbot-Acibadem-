import logging
import re
import time

from chat.models import UniversityContent
from chat.vector_store import semantic_search

from .text_cleaning import (
    clean_raw_text,
    extract_relevant_chunks,
    is_test_source,
    normalize_text,
)

logger = logging.getLogger(__name__)

PRIORITY_KEYWORDS = [
    "kontenjan", "puan", "ucret", "burs", "siralam",
    "muhendislik", "tip", "eczacilik",
]

DEPARTMENT_TERMS = {
    "tip": ["tip"],
    "muhendislik": ["muhendislik", "muhendisligi", "muhendisli"],
    "eczacilik": ["eczacilik", "eczaciligi", "eczacili"],
    "fizyoterapi": ["fizyoterapi"],
    "beslenme": ["beslenme"],
    "hemsirelik": ["hemsirelik", "hemsireligi", "hemsireli"],
    "psikoloji": ["psikoloji"],
    "isletme": ["isletme"],
    "iktisat": ["iktisat"],
    "hukuk": ["hukuk"],
    "gastronomi": ["gastronomi"],
    "mimarlik": ["mimarlik", "mimarligi", "mimarli"],
}


def has_priority_keyword(normalized_text: str) -> bool:
    return any(kw in normalized_text for kw in PRIORITY_KEYWORDS)


def first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return next((group for group in match.groups() if group), None)
    return None


def direct_answer_from_context(user_text: str, context_text: str) -> str | None:
    """Return deterministic answers for critical manual data instead of involving the LLM."""
    normalized = normalize_text(user_text)
    context = clean_raw_text(context_text)

    asks_about_admission_facts = any(
        keyword in normalized
        for keyword in ["kontenjan", "puan", "ucret", "burs", "siralam"]
    )
    if not asks_about_admission_facts:
        return None

    if "tip" in normalized:
        program = "Tıp Fakültesi"
    elif "hemsirelik" in normalized:
        program = "Hemşirelik Bölümü"
    elif "muhendislik" in normalized:
        program = "Bilgisayar Mühendisliği Bölümü"
    else:
        program = "İlgili program"

    if "kontenjan" in normalized:
        total = first_match(context, [
            r"toplam öğrenci kontenjanı\D{0,40}(\d+)",
            r"toplam kontenjan\D{0,40}(\d+)",
            r"kontenjan\D{0,40}(\d+) kişidir",
        ])
        full_scholarship = first_match(context, [
            r"(\d+)\s*(?:kişi|tanesi)?\s*Tam Burslu",
        ])
        discounted = first_match(context, [
            r"(\d+)\s*(?:kişi|tanesi)?\s*(?:ise\s*)?%50 İndirimli",
        ])

        if total:
            pieces = [f"{program} için toplam kontenjan {total} kişidir."]
            if full_scholarship and discounted:
                pieces.append(f"Kontenjanın {full_scholarship} kişisi Tam Burslu, {discounted} kişisi %50 İndirimlidir.")
            if "ingilizce" in normalize_text(context):
                pieces.append("Eğitim dili İngilizcedir.")
            return " ".join(pieces)

    return None


def rerank_docs(results: list[dict], user_text: str) -> list[dict]:
    query_words = set(normalize_text(user_text).split())
    scored = []
    for item in results:
        doc_normalized = normalize_text(item["text"])
        score = sum(1 for w in query_words if w in doc_normalized)
        
        # Ağırlıklandırma (Weighting): Ana site ve Extra linklere öncelik ver
        source = item.get("source", "")
        if source.startswith("Extra:"):
            score += 20  # En yüksek öncelik
        elif source.startswith("Ana:") or source.startswith("Alt:"):
            score += 3
        elif source.startswith("OBS:"):
            score += 0  # OBS'ye ekstra puan yok
            
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


def active_departments(normalized_query: str) -> list[str]:
    return [
        dept for dept, terms in DEPARTMENT_TERMS.items()
        if any(term in normalized_query for term in terms)
    ]


def db_sources_for_departments(departments: list[str]) -> list[dict]:
    if not departments:
        return []

    results = []
    try:
        for content in UniversityContent.objects.all():
            if is_test_source(content.source_name, content.raw_text):
                continue
            content_norm = normalize_text(f"{content.source_name}\n{content.raw_text}")
            if any(
                term in content_norm
                for dept in departments
                for term in DEPARTMENT_TERMS[dept]
            ):
                results.append({"text": content.raw_text, "source": content.source_name})
    except Exception as e:
        logger.debug("DB source boost skipped: %s", e)
    return results


def build_context(user_text: str, n_results: int = 10) -> tuple[str, list[str]]:
    """Build RAG context with semantic search, DB source boost, filtering and reranking."""
    started_at = time.perf_counter()
    normalized_query = normalize_text(user_text)
    departments = active_departments(normalized_query)
    db_boosted_results = db_sources_for_departments(departments)

    try:
        search_started_at = time.perf_counter()
        results = semantic_search(user_text, n_results=n_results)
        logger.info(
            "ChromaDB semantic_search completed in %.2fs with %d result(s)",
            time.perf_counter() - search_started_at,
            len(results),
        )
    except Exception as e:
        logger.exception("ChromaDB search failed: %s", e)
        results = []


    if not results and not db_boosted_results:
        return "", []



    return "\n\n".join([r["text"] for r in results]), [r["source"] for r in results]

    # return "".join(results), []

    # strict_filtered = []
    # seen_sources = set()
    # for item in db_boosted_results + results:
    #     if item["source"] in seen_sources:
    #         continue
    #     seen_sources.add(item["source"])

    #     doc_text_norm = normalize_text(item["text"])
    #     source_norm = normalize_text(item["source"])
    #     if is_test_source(item["source"], item["text"]):
    #         continue

    #     if departments:
    #         if not any(
    #             term in doc_text_norm
    #             for dept in departments
    #             for term in DEPARTMENT_TERMS[dept]
    #         ):
    #             continue

    #         if "tip" in departments:
    #             if any(bad in source_norm for bad in ["beslenme", "diyetetik", "duyurular"]):
    #                 continue

    #     strict_filtered.append(item)

    # if not strict_filtered:
    #     return "", []

    # results = rerank_docs(strict_filtered, user_text)
    # words = [w for w in user_text.split() if len(w) > 2]
    # parts = []
    # sources = []
    # for item in results:
    #     clean = clean_raw_text(item["text"])
    #     clean = extract_relevant_chunks(clean, words)
    #     if len(clean) > 100:
    #         source_name = item["source"]
    #         # Metin Analizi Etiketi Ekleme (LLM'e kaynağın doğasını belirtmek için)
    #         if source_name.startswith("Extra:") or source_name.startswith("Ana:") or source_name.startswith("Alt:"):
    #             clean = f"[GENEL BİLGİ - ANA SİTE] {clean}"
    #         elif source_name.startswith("OBS:"):
    #             clean = f"[DERS BİLGİSİ - BOLOGNA OBS] {clean}"
    #         elif source_name.startswith("Manuel:"):
    #             clean = f"[ÖZEL BİLGİ - MANUEL KAYIT] {clean}"
                
    #         parts.append(clean[:1800])
    #         sources.append(source_name)

    # context_text = "\n--- SAYFA AYRACI ---\n".join(parts)
    # logger.info(
    #     "RAG context built in %.2fs using %d source(s), %d chars",
    #     time.perf_counter() - started_at,
    #     len(set(sources)),
    #     len(context_text),
    # )

