# Acıbadem Üniversitesi Asistanı (RAG Destekli Chatbot)

Bu proje, Acıbadem Üniversitesi için geliştirilmiş, yerel modeller (Ollama) ve PostgreSQL kullanılarak oluşturulmuş bir RAG (Retrieval-Augmented Generation) tabanlı sohbet botudur. 

## 🚀 Son Güncellemeler ve İyileştirmeler (Takım Bilgilendirmesi)

Sistemin RAG altyapısında kapsamlı mimari değişiklikler yapılmış ve performans sorunları giderilmiştir:

1. **PostgreSQL Full-Text Search Entegrasyonu:**
   - Eski ve verimsiz olan `icontains` tabanlı arama yerine, Django'nun yerleşik `SearchVector` ve `SearchRank` özellikleri entegre edildi.
   - Bu sayede kullanıcının girdiği kelimeler semantik olarak ağırlıklandırılarak (Rank) en ilgili sayfaların getirilmesi sağlandı.

2. **Bağlamsal Arama (Contextual Query Expansion):**
   - *"Kaç kişi alıyor peki?"* gibi takip sorularında botun bağlamı (context) kaybetmemesi için arama mantığı güncellendi.
   - Artık arka planda arama yapılırken, kullanıcının bir önceki sorusu ile mevcut sorusu birleştirilip veritabanına gönderiliyor (Geçmiş belleği).

3. **Akıllı Veri Çekme (Scraper) İyileştirmesi:**
   - `sync_data.py` tamamen baştan yazıldı.
   - Hedef sayfalardaki mega menüler, footer ve gereksiz navigasyon elementleri LLM'in kafasını karıştırdığı için `sidebar-page-content` bazlı akıllı ayrıştırma (parsing) mekanizması eklendi.
   - Sayfalardaki HTML tabloları `|` ile markdown formatına yakın bir düzene çevrilerek LLM'in tablo okuma yeteneği artırıldı.
   - Önemsiz "Ana Sayfa" gibi yönlendirme sayfaları RAG gürültüsünü önlemek için filtre dışı bırakıldı.

4. **Prompt Engineering ve Halüsinasyon Kontrolü:**
   - Ollama `gemma:2b` gibi hafif modellerin veritabanında olmayan bilgiler hakkında "uydurma" (hallucination) yapmasını engellemek için sistem promptu katılaştırıldı.
   - Metinde geçmeyen isim, numara veya başlıklar sorulduğunda modelin doğrudan *"Sistemimde bu bilgi bulunmuyor"* demesi sağlandı.
   - Tarayıcı geçmişinden kaynaklanan halüsinasyon sızıntıları temizlendi.

---

## 🛠 Kurulum ve Çalıştırma

**Ön Şartlar:**
- Docker ve Docker Compose

1. **Projeyi Başlatın:**
   ```bash
   docker-compose up -d
   ```

2. **Verileri Çekin (Scraper):**
   *(Veritabanının boş olduğu veya güncellenmesi gerektiği durumlarda)*
   ```bash
   docker-compose exec webapp python sync_data.py
   ```
   > **Not:** `sync_data.py`'nin çalışabilmesi için önce `/admin` panelinden `University links` kısmına taranacak ana bağlantıların eklenmiş olması gerekmektedir.

3. **Kullanım:**
   - Web arayüzü: `http://localhost:8000/`
   - Admin paneli: `http://localhost:8000/admin` (Kullanıcı: admin / Şifre: 1234)

## 🏗 Teknolojiler
- **Backend:** Django, PostgreSQL
- **LLM Engine:** Ollama (Gemma 2B vb.)
- **RAG:** PostgreSQL Full-Text Search (`SearchVector`, `SearchRank`)
- **Scraper:** BeautifulSoup4