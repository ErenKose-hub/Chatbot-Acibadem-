import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from scraper.sync_data import get_content_and_links

url = "https://www.acibadem.edu.tr/akademik/lisans/muhendislik-ve-doga-bilimleri-fakultesi/bilgisayar-muhendisligi"
text, _ = get_content_and_links(url)

print("==== KANIT: BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜM BAŞKANI ====")
if text:
    print(f"\n[DEBUG] URL: {url} | Çekilen Metin Uzunluğu: {len(text)}")
    for line in text.split("\n"):
        if "Bölüm Başkanı" in line or "Baskan" in line or "Başkanı" in line or "Demirel" in line or "Tuğrul" in line:
            print("Bulunan Satır:", line)
else:
    print("Metin çekilemedi!")
