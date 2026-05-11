#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# entrypoint.sh — Acıbadem Chatbot webapp başlatma scripti
#
# Görevler:
#   1. Ollama servisinin hazır olmasını bekle (retry loop)
#   2. Varsayılan modeli çek (zaten varsa Ollama anında "already exists" döner)
#   3. Django'yu başlat
# ──────────────────────────────────────────────────────────────────────────────
set -e

OLLAMA_URL="${OLLAMA_BASE_URL:-http://acu-llm:11434}"
MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
MAX_RETRIES=20
RETRY_INTERVAL=3

echo "[Entrypoint] Ollama servisi bekleniyor: ${OLLAMA_URL}"

for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
        echo "[Entrypoint] Ollama hazır (${i}. deneme)."
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "[Entrypoint] UYARI: Ollama ${MAX_RETRIES} denemede yanıt vermedi. Devam ediliyor..."
        break
    fi
    echo "[Entrypoint] Ollama henüz hazır değil. ${RETRY_INTERVAL}s bekleniyor... (${i}/${MAX_RETRIES})"
    sleep $RETRY_INTERVAL
done

echo "[Entrypoint] Model çekiliyor: ${MODEL}"
curl -sf -X POST "${OLLAMA_URL}/api/pull" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${MODEL}\"}" > /dev/null 2>&1 && \
    echo "[Entrypoint] Model hazır: ${MODEL}" || \
    echo "[Entrypoint] UYARI: Model pull başarısız (zaten mevcut olabilir)."

echo "[Entrypoint] Django başlatılıyor..."
exec python manage.py runserver 0.0.0.0:8000
