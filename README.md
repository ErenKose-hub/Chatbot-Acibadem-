# Acıbadem Üniversitesi Akademik Asistanı (Modern RAG Pipeline)

Bu proje, Acıbadem Üniversitesi için geliştirilmiş; yerel LLM (Ollama), ChromaDB Vektör Veritabanı ve PostgreSQL hibrit yapısını kullanan ileri seviye bir RAG (Retrieval-Augmented Generation) sohbet robotudur.

## 🚀 Öne Çıkan Mimari Özellikler

Sistem, akademik verilerin doğruluğunu korumak ve halüsinasyonları (uydurma cevaplar) engellemek için çok katmanlı bir filtreleme mekanizmasına sahiptir:

1. **Hibrit Veri Besleme (Web + Manuel):**
   - **Web Scraper:** `sync_data.py` ile üniversite web sitesinden dinamik veri çekimi.
   - **Manual Data:** `manual_data/` klasörüne eklenen `.txt` dosyaları, `sync_manual_data()` fonksiyonu ile otomatik olarak sisteme dahil edilir. Bu özellik, webde bulunmayan veya çok kritik olan "temiz" verilerin sisteme enjekte edilmesini sağlar.

2. **Gelişmiş Vektör Arama ve Chunking:**
   - **ChromaDB:** Tüm veriler `paraphrase-multilingual-MiniLM-L12-v2` modeli ile vektörleştirilerek ChromaDB'de saklanır.
   - **Akıllı Chunking:** Veriler, bölüm bazlı (Tıp, Mühendislik vb.) parçalara ayrılarak kaydedilir. Böylece arama sonuçlarında farklı bölümlerin verilerinin birbirine karışması önlenir.

3. **Dinamik Filtreleme ve Cross-Check:**
   - Kullanıcı sorusundaki anahtar kelimeler (örn: "Tıp") ile arama sonuçları arasında sıkı bir eşleşme kontrolü yapılır. İlgili anahtar kelimeyi içermeyen dökümanlar context'ten otomatik olarak elenir.

4. **Kaynak İzlenebilirliği (Debug Mode):**
   - Botun verdiği her cevabın altında, bilginin hangi kaynaktan (URL veya Manuel Dosya) alındığı otomatik olarak eklenir. Bu sayede verinin doğruluğu anlık olarak denetlenebilir.

---

## 🛠 Docker ve Kurulum

### Volume Mount İşlemi
`docker-compose.yml` üzerinde yapılan yapılandırma ile yerel `manual_data/` klasörü konteyner içindeki `/app/manual_data` dizinine bağlanmıştır. Bu sayede konteynerı durdurmadan veri dosyası ekleyebilirsiniz.

### Senkronizasyonu Tetikleme
Yeni eklediğiniz manuel dosyaların veya güncellenen web sayfalarının sisteme işlenmesi için şu komutu çalıştırın:
```bash
docker exec acibadem-chatbot-webapp-1 python sync_data.py
```

---

## 🧼 Hata Giderme (Troubleshooting)

Veri kirliliği oluştuğunda veya sistemi sıfırdan başlatmak istediğinizde aşağıdaki "Nükleer Temizlik" adımlarını uygulayabilirsiniz:

### 1. PostgreSQL Verilerini Temizleme (Django Shell)
```bash
docker exec -it acibadem-chatbot-webapp-1 python manage.py shell
>>> from chat.models import UniversityContent
>>> UniversityContent.objects.all().delete()
```

### 2. ChromaDB Vektörlerini Sıfırlama
```bash
# Proje kök dizininde
rm -rf webapp/db/chroma/*
```

---

## 🏗 Teknolojiler
- **Backend:** Django, PostgreSQL
- **LLM Engine:** Ollama (Gemma:2b)
- **Vektör Deposu:** ChromaDB
- **Embedding:** sentence-transformers (MiniLM-L12)
- **Scraper:** BeautifulSoup4 & Requests