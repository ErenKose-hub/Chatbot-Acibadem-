import os
import django
import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Django Ayarları
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from chat.models import UniversityLink, UniversityContent

# Gürültü olarak değerlendirilen tag'ler
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "iframe"]

# Gürültü class/id kalıpları (kısmi eşleşme)
NOISE_PATTERNS = ["sidebar-menu", "mobil-breadcrumb", "breadcrumb-wrapper", "footer-content"]

# Alt sayfa URL'lerinde aranacak anahtar kelimeler
LINK_KEYWORDS = ["kontenjan", "puan", "akademik", "kadro", "ogretim", "bolum", "ders", "ucret", "program", "fakulte"]

# Minimum anlamlı metin uzunluğu
MIN_TEXT_LENGTH = 300


def clean_soup(soup):
    """Sayfadan gürültü tag ve class'larını temizler."""
    # Tag bazlı temizlik
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    # Class/ID bazlı temizlik
    for pattern in NOISE_PATTERNS:
        for el in soup.find_all(True, class_=lambda c: c and any(pattern in cls.lower() for cls in (c if isinstance(c, list) else [c]))):
            el.decompose()
        for el in soup.find_all(True, id=lambda i: i and pattern in i.lower()):
            el.decompose()

    # Tabloları LLM için okunabilir ( | formatında) metne çevir
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            for td in tr.find_all(["td", "th"]):
                td.insert(0, " | ")
            tr.append("\n")

    return soup


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

    for base in base_links:
        print(f"\n[ANA SAYFA] {base.title} → {base.url}")
        main_text, sub_links = get_content_and_links(base.url)

        if main_text:
            UniversityContent.objects.update_or_create(
                source_name=f"Ana: {base.title}",
                defaults={"raw_text": main_text}
            )
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
                UniversityContent.objects.update_or_create(
                    source_name=f"Alt: {sub}",
                    defaults={"raw_text": sub_text}
                )
                total_saved += 1
                print(f"    ✓ Kaydedildi ({len(sub_text)} karakter)")
            else:
                print(f"    ✗ Yetersiz içerik ({len(sub_text) if sub_text else 0} karakter), atlandı.")

    print(f"\n{'=' * 60}")
    print(f"  Tamamlandı. Toplam {total_saved} kayıt güncellendi/eklendi.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    sync_deep()