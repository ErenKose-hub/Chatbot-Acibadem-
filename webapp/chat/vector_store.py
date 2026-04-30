"""
ChromaDB Vektör Deposu — Merkezi Modül

Bu modül şunları sağlar:
  - get_chroma_collection()  : Singleton ChromaDB koleksiyon referansı
  - get_embedding(text)      : Metni vektöre çevirir
  - upsert_content(...)      : Bir UniversityContent kaydını ChromaDB'ye yazar/günceller
  - semantic_search(query)   : En yakın N belgeyi cosine benzerliğiyle döndürür
"""

import os
from sentence_transformers import SentenceTransformer
import chromadb

# ── Yapılandırma ──────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "db/chroma")
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "university_content"

# ── Singleton nesneleri (modül seviyesinde bir kez başlatılır) ────────────────
_model: SentenceTransformer | None = None
_collection = None


def _get_model() -> SentenceTransformer:
    """Embedding modelini yükler; sonraki çağrılarda önbellekten kullanır."""
    global _model
    if _model is None:
        print(f"[VectorStore] Embedding modeli yükleniyor: {EMBEDDING_MODEL_NAME}")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def get_chroma_collection():
    """ChromaDB koleksiyonunu döndürür; yoksa oluşturur (cosine benzerliği)."""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[VectorStore] Koleksiyon hazır: '{COLLECTION_NAME}' "
              f"({_collection.count()} belge) → {CHROMA_PERSIST_DIR}")
    return _collection


def get_embedding(text: str) -> list[float]:
    """Verilen metni embedding vektörüne çevirir."""
    return _get_model().encode(text, show_progress_bar=False).tolist()


def upsert_content(source_name: str, text: str) -> None:
    """
    Bir UniversityContent kaydını parçalara (chunks) ayırarak ChromaDB'ye yazar.
    Bu, Tıp ve Hemşirelik gibi farklı bölümlerin aynı paket içinde LLM'e gitmesini engeller.
    """
    collection = get_chroma_collection()

    # --- CHUNKING STRATEJİSİ ---
    if "--- KAYIT ---" in text:
        # CSV veya KV formatındaki verileri kayıt bazlı böl
        chunks = [c.strip() for c in text.split("--- KAYIT ---") if len(c.strip()) > 40]
    else:
        # Düz metinleri ~1500 karakterlik parçalara böl (200 karakter overlap ile)
        chunks = []
        chunk_size = 1500
        overlap = 200
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end].strip())
            start += (chunk_size - overlap)

    for idx, chunk in enumerate(chunks):
        # Her parça için benzersiz ID üret
        clean_name = source_name[:100].replace("/", "_").replace(" ", "_")
        doc_id = f"{clean_name}_{idx}"
        
        # Embedding ve Kayıt
        embedding = get_embedding(chunk[:2000])
        collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[chunk],
            metadatas=[{"source": source_name, "chunk_idx": idx}],
        )

    print(f"  [VectorStore] {source_name[:50]}… → {len(chunks)} parçaya bölündü.")


def semantic_search(query: str, n_results: int = 2) -> list[dict]:
    """
    Kullanıcı sorgusuna anlamsal olarak en yakın n_results belgeyi döndürür.
    Koleksiyon boşsa boş liste döner (graceful fallback).

    Returns:
        list[dict]: [{'text': '...', 'source': '...'}, ...] formatında sonuçlar.
    """
    collection = get_chroma_collection()
    count = collection.count()

    if count == 0:
        print("[VectorStore] Koleksiyon boş; önce sync_data.py çalıştırın.")
        return []

    query_embedding = get_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, count),
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    # Çok uzak (alakasız) sonuçları filtrele: cosine distance > 1.2 → atla
    filtered = []
    for doc, meta, dist in zip(docs, metadatas, distances):
        if dist <= 1.2:
            filtered.append({
                "text": doc,
                "source": meta.get("source", "Bilinmeyen Kaynak")
            })
    return filtered
