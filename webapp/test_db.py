import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from chat.models import UniversityContent

contents = UniversityContent.objects.filter(source_name__icontains="bilgisayar")
print(f"Bulunan bilgisayar içerik sayısı: {contents.count()}")

for c in contents:
    print(f"--- {c.source_name} ---")
    lines = c.raw_text.split('\n')
    for line in lines:
        if "Başkan" in line or "Baskan" in line or "Tuğrul" in line or "Demirel" in line:
            print("BULUNDU:", line)
