import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from chat.models import UniversityContent

def extract_chunks(text, words):
    if "--- KAYIT ---" in text:
        chunks = text.split("--- KAYIT ---")
        relevant_chunks = [chunks[0][:500]] # Ana metinden sadece 500 karakter
        search_keywords = [w.lower() for w in words]
        for chunk in chunks[1:]:
            chunk_lower = chunk.lower()
            if any(kw in chunk_lower for kw in search_keywords):
                relevant_chunks.append(chunk.strip())
        return "\n--- KAYIT ---\n".join(relevant_chunks)
    return text[:3000]

obj = UniversityContent.objects.get(source_name__icontains="kontenjan")
words = ["bilgisayar", "mühendisliği", "kontenjanı"]
res = extract_chunks(obj.raw_text, words)
print("EXTRACTED LENGTH:", len(res))
print(res)
