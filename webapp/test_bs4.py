import requests
import re
from bs4 import BeautifulSoup

NOISE_TAGS = ["script", "style", "nav", "footer", "header", "form", "noscript", "iframe", "button"]
NOISE_PATTERNS = [
    "mobil-breadcrumb", "breadcrumb-wrapper", "footer-content",
    "sticky", "cookie", "popup", "modal", "overlay", "social", "share",
    "search-bar", "language-switch", "quick-links", "hizli-erisim",
]
BUTTON_TEXT_PATTERNS = [
    r"Sor Cevaplayalım", r"Başvuru Yap", r"Giriş", r"\bGiriş\b", r"Üye Ol",
    r"Kaydol", r"Detay", r"Daha Fazla", r"Tümü Gör", r"Yükle",
    r"Ara\.\.\.", r"Arama", r"Menu", r"Menü",
]

def clean_soup(soup):
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    for pattern in NOISE_PATTERNS:
        for el in soup.find_all(True, class_=lambda c: c and any(pattern in cls.lower() for cls in (c if isinstance(c, list) else [c]))):
            el.decompose()
        for el in soup.find_all(True, id=lambda i: i and pattern in i.lower()):
            el.decompose()
    button_regex = re.compile("|".join(BUTTON_TEXT_PATTERNS), flags=re.IGNORECASE)
    for el in soup.find_all(["a", "span", "li", "div", "p"]):
        if el.get_text(strip=True) and button_regex.fullmatch(el.get_text(strip=True)):
            el.decompose()
    return soup

def extract_main_content(soup):
    if soup.body:
        text = " ".join(soup.body.get_text(separator=" ", strip=True).split())
    else:
        text = " ".join(soup.get_text(separator=" ", strip=True).split())
    if len(text) >= 300:
        return text
    return None

url = "https://www.acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bilgisayar-muhendisligi"
res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
res.encoding = res.apparent_encoding
soup = BeautifulSoup(res.text, "html.parser")
soup = clean_soup(soup)
text = extract_main_content(soup)

print("==== KANIT: BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜM BAŞKANI ====")
if text:
    print(f"\n[DEBUG] URL: {url} | Çekilen Metin Uzunluğu: {len(text)}")
    for sentence in text.split(". "):
        if "Başkan" in sentence or "Baskan" in sentence or "Tuğrul" in sentence:
            print("Bulunan Cümle:", sentence)
else:
    print("Metin çekilemedi!")
