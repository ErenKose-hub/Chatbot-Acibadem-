# manual_data/ — Manuel Veri Klasörü

Bu klasöre koyduğunuz her `.txt` dosyası, `sync_data.py` çalıştırıldığında
otomatik olarak hem PostgreSQL'e hem de ChromaDB'ye yüklenir.

## Kullanım

1. Temiz, düz metin içerikli bir `.txt` dosyası hazırlayın.
2. Dosyayı bu klasöre kopyalayın.
3. `docker exec acibadem-chatbot-webapp-1 python sync_data.py` komutunu çalıştırın.

## Dosya Adlandırma Kuralı

Dosya adı, sistemdeki kayıt adı (source_name) olarak kullanılır.
Örnek: `tip_fakultesi_kontenjan_2024.txt` → kaynak adı: `Manuel: tip_fakultesi_kontenjan_2024`

## Format Önerileri

- Düz metin, satır bazlı bilgiler tercih edilir.
- Tablo verilerini şu KV formatında yazabilirsiniz:
    Bölüm: Tıp Fakültesi
    Kontenjan (Burslu): 40
    Kontenjan (%50 İndirimli): 15
- Her kayıt bloğunu boş bir satırla ayırın.
