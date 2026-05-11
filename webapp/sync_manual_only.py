import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from sync_data import sync_manual_data, sync_admin_contents

if __name__ == "__main__":
    print("Sadece manuel veriler senkronize ediliyor...")
    sync_manual_data()
    sync_admin_contents()
    print("Bitti.")
