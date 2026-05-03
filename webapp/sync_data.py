import os
import django
import requests
import time
import csv
import io
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Django Ayarları
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from chat.models import UniversityLink, UniversityContent
from chat.vector_store import upsert_content

# Gürültü olarak değlendirilen tag'ler
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "iframe", "button"]

# Gürültü class/id kalıpları (kısmi eşleşme)
NOISE_PATTERNS = [
    "sidebar-menu", "mobil-breadcrumb", "breadcrumb-wrapper", "footer-content",
    "sticky", "cookie", "popup", "modal", "overlay", "social", "share",
    "search-bar", "language-switch", "quick-links", "hizli-erisim",
]

# Buton / CTA metin kalıpları — bu metinleri içeren tag'leri sil
BUTTON_TEXT_PATTERNS = [
    r"Sor Cevaplayalım", r"Başvuru Yap", r"Giriş", r"\bGiriş\b", r"Üye Ol",
    r"Kaydol", r"Detay", r"Daha Fazla", r"Tümü Gör", r"Yükle",
    r"Ara\.\.\.", r"Arama", r"Menu", r"Menü",
]

# Alt sayfa URL'lerinde aranacak anahtar kelimeler
LINK_KEYWORDS = ["kontenjan", "puan", "akademik", "kadro", "ogretim", "bolum", "ders", "ucret", "program", "fakulte"]

# Her senkronizasyonda mutlaka çekilecek kritik URL'ler (DB'de link kaydı olmasa bile)
EXTRA_URLS = [
    "https://www.acibadem.edu.tr/aday/ogrenci/egitim/lisans/lisans-kontenjan-ve-puan-tablosu",
    "https://www.acibadem.edu.tr/akademik/lisans",
]

# Minimum anlamlı metin uzunluğu
MIN_TEXT_LENGTH = 300


def clean_soup(soup):
    """Sayfadan gürültü tag ve class'ı ile buton/navigasyon metinlerini temizler."""
    import re as _re

    # Tag bazlı temizlik (button tag da dahil edildi)
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    # Class/ID bazlı temizlik
    for pattern in NOISE_PATTERNS:
        for el in soup.find_all(True, class_=lambda c: c and any(pattern in cls.lower() for cls in (c if isinstance(c, list) else [c]))):
            el.decompose()
        for el in soup.find_all(True, id=lambda i: i and pattern in i.lower()):
            el.decompose()

    # Buton / CTA metni taşıyan öğeleri sil (a, span, div, li vb.)
    button_regex = _re.compile(
        "|".join(BUTTON_TEXT_PATTERNS), flags=_re.IGNORECASE
    )
    for el in soup.find_all(["a", "span", "li", "div", "p"]):
        if el.get_text(strip=True) and button_regex.fullmatch(el.get_text(strip=True)):
            el.decompose()

    # Tabloları LLM için okunabilir ( | formatında) metne çevir
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            for td in tr.find_all(["td", "th"]):
                td.insert(0, " | ")
            tr.append("\n")

    return soup

def fetch_and_parse_csv(csv_url):
    """CSV dosyasını indirir, ayıracını otomatik tespit eder ve okunabilir KV (Key-Value) metne çevirir."""
    try:
        res = requests.get(csv_url, timeout=10)
        res.encoding = "utf-8"
        csv_data = res.text
        
        # Dialect ve delimiter'ı bul (noktalı virgül mü virgül mü)
        dialect = csv.Sniffer().sniff(csv_data[:1024])
        reader = csv.reader(io.StringIO(csv_data), dialect)
        
        table_text = "\n[CSV VERİSİ BAŞLANGICI]\n"
        headers = []
        
        for i, row in enumerate(reader):
            if not any(row):  # Boş satırları atla
                continue
                
            # İlk dolu satırı başlık (header) kabul et
            if not headers:
                headers = [h.strip() for h in row]
                continue
                
            # Alt satırları KV formatına çevir
            table_text += "--- KAYIT ---\n"
            for j, cell in enumerate(row):
                if cell.strip():
                    header_name = headers[j] if j < len(headers) and headers[j] else f"Sütun {j+1}"
                    table_text += f"{header_name}: {cell.strip()}\n"
                    
        table_text += "[CSV VERİSİ BİTİŞİ]\n"
        return table_text
    except Exception as e:
        print(f"      [CSV Hatası] {csv_url}: {e}")
        return ""


def extract_main_content(soup):
    """
    Sayfanın asıl içerik bloğunu bulmaya çalışır.
    Önce semantik tag'leri dener, bulamazsa tüm body'ye düşer.
    """
    # Öncelik sırası: <div class="sidebar-page-content"> → <main> → <article>
    candidates = [
        soup.find("div", class_=lambda c: c and "sidebar-page-content" in c),
        soup.find("main"),
        soup.find("article"),
        soup.find(attrs={"role": "main"}),
        soup.find("div", id=lambda i: i and "content" in i.lower()),
        soup.body,
    ]

    for candidate in candidates:
        if candidate:
            text = " ".join(candidate.get_text(separator=" ", strip=True).split())
            if len(text) >= MIN_TEXT_LENGTH:
                return text

    return None


def sync_manual_data():
    """manual_data/ klasörü altındaki .txt dosyalarını okur ve hem DB'ye hem ChromaDB'ye kaydeder."""
    manual_dir = "/app/manual_data"
    if not os.path.exists(manual_dir):
        print(f"\n[MANUEL VERİ] Klasör bulunamadı: {manual_dir}")
        return 0

    files = [f for f in os.listdir(manual_dir) if f.endswith(".txt")]
    if not files:
        print(f"\n[MANUEL VERİ] İşlenecek .txt dosyası bulunamadı.")
        return 0

    print(f"\n[MANUEL VERİ] {len(files)} dosya işleniyor...")
    count = 0
    for filename in files:
        filepath = os.path.join(manual_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if len(content) < 10:
                print(f"  ✗ {filename} (Çok kısa içerik, atlandı)")
                continue

            source_name = f"Manuel: {filename}"
            UniversityContent.objects.update_or_create(
                source_name=source_name,
                defaults={"raw_text": content}
            )
            upsert_content(source_name, content)
            count += 1
            print(f"  ✓ {filename} ({len(content)} karakter)")
        except Exception as e:
            print(f"  ✗ {filename} (Hata: {e})")
    
    return count


def get_content_and_links(url):
    """Sayfa içeriğini çeker, temizler ve içindeki alakalı linkleri bulur."""
    try:
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; AcibademBot/1.0)"})
        res.encoding = res.apparent_encoding  # Türkçe karakter bozulmasını önle
        soup = BeautifulSoup(res.text, "html.parser")

        # Gürültü temizliği
        soup = clean_soup(soup)

        # Asıl içerik bloğunu çıkar
        clean_text = extract_main_content(soup)
        
        # Eğer sayfada CSV linki varsa (dinamik yüklenen tablolar), indirip metne ekle
        for a in soup.find_all("a", href=True):
            if a["href"].endswith(".csv"):
                csv_url = urljoin(url, a["href"])
                csv_content = fetch_and_parse_csv(csv_url)
                if csv_content and clean_text:
                    clean_text += "\n" + csv_content

        # Linkleri topla (link çekme temiz soup üzerinden yapılır)
        links = []
        for a in soup.find_all("a", href=True):
            full_url = urljoin(url, a["href"])
            if any(key in full_url.lower() for key in LINK_KEYWORDS):
                links.append(full_url)

        return clean_text, list(set(links))

    except Exception as e:
        print(f"  [HATA] ({url}): {e}")
        return None, []


def sync_deep():
    print("=" * 60)
    print("  Derin ve Temiz Senkronizasyon Başladı")
    print("=" * 60)

    base_links = UniversityLink.objects.all()
    total_saved = 0



    # --- 4. Admin İçeriklerini İşle ---
    admin_count = sync_admin_contents()
    total_saved += admin_count

   
   
   
    # --- 1. DB'deki ana bağlantıları işle ---
    for base in base_links:
        print(f"\n[ANA SAYFA] {base.title} → {base.url}")
        main_text, sub_links = get_content_and_links(base.url)

        if main_text:
            source = f"Ana: {base.title}"
            UniversityContent.objects.update_or_create(
                source_name=source,
                defaults={"raw_text": main_text}
            )
            upsert_content(source, main_text)   # ChromaDB'ye vektörleştir
            total_saved += 1
            print(f"  ✓ Kaydedildi ({len(main_text)} karakter)")
        else:
            print(f"  ✗ Anlamlı içerik bulunamadı, atlandı.")

        # Her ana sayfadan max 10 alt sayfa
        for sub in sub_links[:10]:
            print(f"  → Alt sayfa: {sub}")
            time.sleep(1.5)  # Sorumlu kazıma
            sub_text, _ = get_content_and_links(sub)

            if sub_text and len(sub_text) >= MIN_TEXT_LENGTH:
                source = f"Alt: {sub}"
                UniversityContent.objects.update_or_create(
                    source_name=source,
                    defaults={"raw_text": sub_text}
                )
                upsert_content(source, sub_text)   # ChromaDB'ye vektörleştir
                total_saved += 1
                print(f"    ✓ Kaydedildi ({len(sub_text)} karakter)")
            else:
                print(f"    ✗ Yetersiz içerik ({len(sub_text) if sub_text else 0} karakter), atlandı.")

    # --- 2. Kritik URL'leri mutlaka çek (Tıp Fakültesi, Kontenjan Tablosu vb.) ---
    print(f"\n[EXTRA URL'LER] {len(EXTRA_URLS)} kritik sayfa zorunlu çekiliyor...")
    for url in EXTRA_URLS:
        print(f"  → {url}")
        time.sleep(1.5)
        extra_text, _ = get_content_and_links(url)
        if extra_text and len(extra_text) >= MIN_TEXT_LENGTH:
            source = f"Extra: {url}"
            UniversityContent.objects.update_or_create(
                source_name=source,
                defaults={"raw_text": extra_text}
            )
            upsert_content(source, extra_text)
            total_saved += 1
            print(f"    ✓ Kaydedildi ({len(extra_text)} karakter)")
        else:
            print(f"    ✗ Yetersiz içerik, atlandı.")

    # --- 3. Manuel Verileri İşle ---
    manual_count = sync_manual_data()
    total_saved += manual_count

    print(f"\n{'=' * 60}")
    print(f"  Tamamlandı. Toplam {total_saved} kayıt güncellendi/eklendi.")
    print(f"  (Web: {total_saved - manual_count}, Manuel: {manual_count})")
    print(f"{'=' * 60}")




def sync_admin_contents():
    """Admin panelinden eklenen UniversityContent kayıtlarını ChromaDB'ye işler."""
    from chat.models import UniversityContent
    
    contents = UniversityContent.objects.all()
    print(f"\n[ADMİN İÇERİKLER] {contents.count()} kayıt işleniyor...")
    count = 0
    for content in contents:
        try:
            upsert_content(content.source_name, content.raw_text)
            count += 1
            print(f"  ✓ {content.source_name}")
        except Exception as e:
            print(f"  ✗ {content.source_name} (Hata: {e})")
    return count

if __name__ == "__main__":
    sync_deep()