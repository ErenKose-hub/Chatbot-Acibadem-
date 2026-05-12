#!/bin/sh
set -e

echo "[Ollama Init] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

echo "[Ollama Init] Waiting for server to be ready..."
for i in $(seq 1 30); do
    if ollama list >/dev/null 2>&1; then
        echo "[Ollama Init] Server is ready."
        break
    fi
    sleep 1
done

echo "[Ollama Init] Checking model: llama3.1:8b"
if ollama list | grep -q "llama3.1:8b"; then
    echo "[Ollama Init] Model already exists."
else
    echo "[Ollama Init] Pulling model: llama3.1:8b"
    ollama pull llama3.1:8b || echo "[Ollama Init] WARNING: Model pull failed, container will continue running."
fi

echo "[Ollama Init] Setup complete. Waiting for server process..."
wait $OLLAMA_PID
