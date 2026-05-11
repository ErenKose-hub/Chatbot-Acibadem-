#!/bin/sh
set -e

echo "[Webapp] Running migrations..."
python manage.py migrate

echo "[Webapp] Checking if data exists..."
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from chat.models import UniversityContent
count = UniversityContent.objects.count()
print(f'[Webapp] UniversityContent count: {count}')
if count == 0:
    exit(1)
" || {
    echo "[Webapp] No data found. Running initial sync..."
    python manage.py sync_data
}

echo "[Webapp] Starting development server..."
python manage.py runserver 0.0.0.0:8000
