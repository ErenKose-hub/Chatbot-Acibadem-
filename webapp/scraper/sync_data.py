import os
import requests
import time
import csv
import io
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.apps import apps
from django.utils import timezone

if not apps.ready:
    import django

    django.setup()

from chat.models import SyncStatus, UniversityLink, UniversityContent
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

OBS_INDEX_URL = "https://obs.acibadem.edu.tr/oibs/bologna/unitSelection.aspx?type=lis&lang=tr"
OBS_SECTION_PAGES = (
    "progAbout.aspx",
    "progCourses.aspx",
)
MAX_OBS_PROGRAMS = 6

# Minimum anlamlı metin uzunluğu
MIN_TEXT_LENGTH = 300


def is_obs_url(url):
    return "obs.acibadem.edu.tr" in url.lower()


def build_obs_section_urls(show_pac_url):
    parsed = re.search(r"curSunit=(\d+)", show_pac_url)
    if not parsed:
        return []

    cur_sunit = parsed.group(1)
    return [
        f"https://obs.acibadem.edu.tr/oibs/bologna/{page}?lang=tr&curSunit={cur_sunit}"
        for page in OBS_SECTION_PAGES
    ]


def discover_obs_program_urls():
    """Discover a small set of public OBS/Bologna undergraduate program pages."""
    try:
        res = requests.get(
            OBS_INDEX_URL,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AcibademBot/1.0)"},
        )
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"  [OBS HATA] Program listesi alınamadı: {e}")
        return []

    selected_programs = []
    seen_program_urls = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "curOp=showPac" not in href:
            continue

        full_url = urljoin(OBS_INDEX_URL, href)
        if full_url in seen_program_urls:
            continue
        seen_program_urls.add(full_url)

        title = " ".join(anchor.get_text(separator=" ", strip=True).split())
        if not title:
            continue

        selected_programs.append((title, full_url))
        if len(selected_programs) >= MAX_OBS_PROGRAMS:
            break

    discovered_urls = []
    for title, show_pac_url in selected_programs:
        section_urls = build_obs_section_urls(show_pac_url)
        if section_urls:
            print(f"  [OBS] Program bulundu: {title}")
            discovered_urls.extend(section_urls)

    return discovered_urls


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


def clean_obs_soup(soup):
    """Keep only the public Bologna content blocks and remove ASP.NET/navigation noise."""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for selector in [
        "#Header1",
        "#Footer1",
        ".navbar",
        ".main-sidebar",
        ".main-header",
        ".main-footer",
        ".preloader",
        ".breadcrumb",
        ".nav",
    ]:
        for el in soup.select(selector):
            el.decompose()

    for hidden in soup.select("input[type='hidden']"):
        hidden.decompose()

    return soup


def extract_obs_content(soup, url):
    """Extract readable public OBS/Bologna program content from iframe pages."""
    soup = clean_obs_soup(soup)
    text_parts = []

    title_candidates = [
        soup.find(["h1", "h2", "h3"]),
        soup.find(id=re.compile(r"lbl.*", re.IGNORECASE)),
        soup.find("strong"),
    ]
    for candidate in title_candidates:
        if candidate:
            title = " ".join(candidate.get_text(separator=" ", strip=True).split())
            if title and title not in text_parts:
                text_parts.append(title)
                break

    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        text = " ".join(tag.get_text(separator=" ", strip=True).split())
        if not text:
            continue
        if text.startswith("__VIEWSTATE") or text.startswith("__EVENT"):
            continue
        if len(text) < 2:
            continue
        text_parts.append(text)

    cleaned_parts = []
    seen = set()
    for text in text_parts:
        if text in seen:
            continue
        seen.add(text)
        cleaned_parts.append(text)

    content = "\n".join(cleaned_parts)
    if len(content) < MIN_TEXT_LENGTH:
        return None

    return f"OBS Kaynağı: {url}\n{content}"

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
    """scraper/manual_data klasörü altındaki .txt dosyalarını okur ve hem DB'ye hem ChromaDB'ye kaydeder."""
    manual_dir = "/app/scraper/manual_data"
    if not os.path.exists(manual_dir):
        print(f"\n[MANUEL VERİ] Klasör bulunamadı: {manual_dir}")
        return 0, 0

    files = [f for f in os.listdir(manual_dir) if f.endswith(".txt")]
    if not files:
        print(f"\n[MANUEL VERİ] İşlenecek .txt dosyası bulunamadı.")
        return 0, 0

    print(f"\n[MANUEL VERİ] {len(files)} dosya işleniyor...")
    count = 0
    chunk_count = 0
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
            chunk_count += upsert_content(source_name, content)
            count += 1
            print(f"  ✓ {filename} ({len(content)} karakter)")
        except Exception as e:
            print(f"  ✗ {filename} (Hata: {e})")
    
    return count, chunk_count


def get_content_and_links(url):
    """Sayfa içeriğini çeker, temizler ve içindeki alakalı linkleri bulur."""
    try:
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; AcibademBot/1.0)"})
        res.encoding = res.apparent_encoding  # Türkçe karakter bozulmasını önle
        soup = BeautifulSoup(res.text, "html.parser")

        if is_obs_url(url):
            clean_text = extract_obs_content(soup, url)
            return clean_text, []

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


def sync_obs_data():
    """Fetch public OBS/Bologna program pages and index them into DB and ChromaDB."""
    obs_urls = discover_obs_program_urls()
    print(f"\n[OBS] {len(obs_urls)} kamuya açık Bologna sayfası işleniyor...")
    saved = 0
    chunk_count = 0

    for url in obs_urls:
        print(f"  → OBS sayfası: {url}")
        time.sleep(1.5)
        obs_text, _ = get_content_and_links(url)

        if obs_text and len(obs_text) >= MIN_TEXT_LENGTH:
            source = f"OBS: {url}"
            UniversityContent.objects.update_or_create(
                source_name=source,
                defaults={"raw_text": obs_text},
            )
            chunk_count += upsert_content(source, obs_text)
            saved += 1
            print(f"    ✓ Kaydedildi ({len(obs_text)} karakter)")
        else:
            print("    ✗ Anlamlı OBS içeriği bulunamadı, atlandı.")

    return saved, chunk_count


def sync_deep():
    started_at = timezone.now()
    status, _ = SyncStatus.objects.get_or_create(key="default")
    status.last_started_at = started_at
    status.last_error = ""
    status.save(update_fields=["last_started_at", "last_error", "updated_at"])

    print("=" * 60)
    print("  Derin ve Temiz Senkronizasyon Başladı")
    print("=" * 60)

    base_links = UniversityLink.objects.all()
    total_saved = 0
    total_chunks = 0

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
            total_chunks += upsert_content(source, main_text)   # ChromaDB'ye vektörleştir
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
                total_chunks += upsert_content(source, sub_text)   # ChromaDB'ye vektörleştir
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
            total_chunks += upsert_content(source, extra_text)
            total_saved += 1
            print(f"    ✓ Kaydedildi ({len(extra_text)} karakter)")
        else:
            print(f"    ✗ Yetersiz içerik, atlandı.")

    # --- 3. Manuel Verileri İşle ---
    manual_count, manual_chunks = sync_manual_data()
    total_saved += manual_count
    total_chunks += manual_chunks

    # --- 4. OBS / Bologna İçeriklerini İşle ---
    obs_count, obs_chunks = sync_obs_data()
    total_saved += obs_count
    total_chunks += obs_chunks

    print(f"\n{'=' * 60}")
    print(f"  Tamamlandı. Toplam {total_saved} kayıt güncellendi/eklendi.")
    print(f"  Toplam {total_chunks} Chroma chunk üretildi/güncellendi.")
    print(f"  (Web: {total_saved - manual_count - obs_count}, Manuel: {manual_count}, OBS: {obs_count})")
    print(f"{'=' * 60}")

    status.last_success_at = timezone.now()
    status.source_count = total_saved
    status.chunk_count = total_chunks
    status.last_error = ""
    status.save(update_fields=["last_success_at", "source_count", "chunk_count", "last_error", "updated_at"])

    return {
        "source_count": total_saved,
        "chunk_count": total_chunks,
        "manual_count": manual_count,
        "obs_count": obs_count,
        "web_count": total_saved - manual_count - obs_count,
    }


if __name__ == "__main__":
    sync_deep()
