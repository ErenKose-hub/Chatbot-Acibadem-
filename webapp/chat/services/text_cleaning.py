import re


def normalize_text(text: str) -> str:
    """Turkish character normalization for matching/search filters."""
    text = text.lower().replace("i̇", "i")
    for src, dst in [("ı", "i"), ("ü", "u"), ("ö", "o"), ("ş", "s"), ("ç", "c"), ("ğ", "g")]:
        text = text.replace(src, dst)
    return text


def clean_raw_text(text: str) -> str:
    """Remove table/navigation noise from DB and ChromaDB snippets."""
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
    """Remove Markdown table remnants and internal test-source noise from model output."""
    text = re.sub(r"\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?", "", text)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"[-]{3,}", "", text)
    text = re.sub(r"(?im)^\s*not:\s*bu veri manuel test dosyas[ıi]d[ıi]r\.?,?", "", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def extract_relevant_chunks(text: str, search_words: list) -> str:
    """For KV/table-like content, return only records matching query words."""
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


def is_test_source(source: str, text: str = "") -> bool:
    normalized = normalize_text(f"{source}\n{text}")
    return "test_veri" in normalized or "manuel test" in normalized
