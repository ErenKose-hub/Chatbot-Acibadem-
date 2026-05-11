# Acıbadem Üniversitesi Akademik Asistanı

Acıbadem Üniversitesi için hazırlanmış Django tabanlı RAG chatbot projesidir. Sistem; PostgreSQL, ChromaDB, SentenceTransformers embedding modeli ve Ollama üzerinde çalışan yerel LLM ile akademik içeriklerden cevap üretir.

## Mimari

- Backend: Django
- Veritabanı: PostgreSQL
- Vektör Deposu: ChromaDB
- Embedding: `paraphrase-multilingual-MiniLM-L12-v2`
- LLM: Ollama `qwen2.5:3b`
- Veri kaynakları: `acibadem.edu.tr` scraping + `obs.acibadem.edu.tr` Bologna scraping + `webapp/scraper/manual_data/*.txt`

## Hızlı Kurulum

Tek komutla başlatma:

```bash
docker compose up -d --build
```

İlk kurulumda:
- Ollama modeli (`qwen2.5:3b`) otomatik indirilir.
- Veritabanı boşsa `sync_data` otomatik çalışır.

Uygulamayı açın:

```text
http://localhost:8000/
```

### Elle kurulum (opsiyonel)

Eğer `.env` dosyası özelleştirmek isterseniz:

```bash
cp .env.example .env
# .env dosyasını düzenleyin
docker compose up -d --build
```

## Sağlık Kontrolü

Sistemin DB, ChromaDB ve Ollama durumunu görmek için:

```text
http://localhost:8000/health/
```

Örnek başarılı çıktı:

```json
{
  "status": "ok",
  "database": {
    "ok": true,
    "university_content_count": 6
  },
  "chroma": {
    "ok": true,
    "document_count": 81
  },
  "ollama": {
    "ok": true,
    "model": "qwen2.5:3b",
    "model_ready": true
  },
  "sync": {
    "ok": true,
    "last_success_at": "2026-05-03T18:33:51.364375+00:00",
    "source_count": 6,
    "chunk_count": 81,
    "last_error": ""
  }
}
```

## Veri Senkronizasyonu

Yeni manuel veri eklediğinizde veya web kaynaklarını yeniden çekmek istediğinizde:

```bash
docker compose exec webapp python manage.py sync_data
```

Manuel veri dosyaları şu klasöre eklenir:

```text
webapp/scraper/manual_data/
```

Sync sırasında:
- `webapp/scraper/manual_data/*.txt` altındaki manuel veriler işlenir.
- `acibadem.edu.tr` üzerindeki ana ve kritik sayfalar çekilir.
- `obs.acibadem.edu.tr` üzerindeki kamuya açık lisans programları otomatik keşfedilir ve Bologna içerikleri indekslenir.

Aynı kaynak tekrar sync edildiğinde eski Chroma chunk'ları temizlenir ve yeniden yazılır.

## Klasör Düzeni

Önemli klasörler:

- `webapp/static/mascot/`: Chat maskot görselleri
- `webapp/scraper/manual_data/`: Manuel bilgi kaynakları

## Test ve Kontrol Komutları

Django sistem kontrolü:

```bash
docker compose exec webapp python manage.py check
```

Testleri çalıştırma:

```bash
docker compose exec webapp python manage.py test chat -v 2
```

DB içerik sayısı:

```bash
docker compose exec webapp python manage.py shell -c "from chat.models import UniversityContent; print(UniversityContent.objects.count())"
```

ChromaDB belge sayısı:

```bash
docker compose exec webapp python -c "from chat.vector_store import get_chroma_collection; print(get_chroma_collection().count())"
```

Ollama modelleri:

```bash
docker compose exec llm-service ollama list
```

## API Kullanımı

JSON endpoint:

```text
POST http://localhost:8000/api/chat/
```

Örnek body:

```json
{
  "message": "Tıp fakültesi kontenjanı kaç?"
}
```

PowerShell örneği:

```powershell
$body = '{"message":"Tip fakultesi kontenjani kac?"}'
Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/api/chat/ -Method POST -ContentType 'application/json; charset=utf-8' -Body $body
```

## Ortam Değişkenleri

Varsayılanlar `.env.example` içinde bulunur.

Önemli değişkenler:

- `DJANGO_DEBUG`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `WEBAPP_PORT`
- `OLLAMA_PORT`
- `OLLAMA_MODEL`
- `CHROMA_PERSIST_DIR`

Production veya dışa açık kullanımda `DJANGO_DEBUG=False`, güçlü `DJANGO_SECRET_KEY` ve güçlü DB şifresi kullanılmalıdır.

## Sorun Giderme

### Bot sürekli veri bulunamadı diyorsa

Önce sağlık kontrolüne bakın:

```text
http://localhost:8000/health/
```

DB veya ChromaDB sayısı `0` ise sync çalıştırın:

```bash
docker compose exec webapp python manage.py sync_data
```

### Ollama modeli yoksa

Model listesini kontrol edin:

```bash
docker compose exec llm-service ollama list
```

Model yoksa indirin:

```bash
docker compose exec llm-service ollama pull qwen2.5:3b
```

### Webapp başlamazsa

Logları okuyun:

```bash
docker compose logs --no-color --tail=100 webapp
```

Servis durumunu kontrol edin:

```bash
docker compose ps
```

### ChromaDB bozulursa veya sıfırlamak gerekirse

Önce webapp'i durdurun:

```bash
docker compose stop webapp
```

Chroma klasörünü temizleyin:

```powershell
Remove-Item -Recurse -Force webapp\db\chroma
New-Item -ItemType Directory -Force webapp\db\chroma
```

Webapp'i açın ve sync çalıştırın:

```bash
docker compose up -d webapp
docker compose exec webapp python manage.py sync_data
```

## Geliştirici Notları

- `chat.views.generate_chat_response()` hem web UI hem JSON API tarafından kullanılır.
- `chat.vector_store.upsert_content()` aynı kaynağı yeniden indekslemeden önce eski chunk'ları temizler.
- `python manage.py sync_data` web, OBS/Bologna ve manuel kaynakları birlikte işler.
- `python manage.py test chat -v 2` text helper ve RAG retrieval testlerini çalıştırır.
