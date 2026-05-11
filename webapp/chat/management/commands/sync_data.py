from django.core.management.base import BaseCommand
from django.utils import timezone

from chat.models import SyncStatus
from scraper.sync_data import sync_deep


class Command(BaseCommand):
    help = "Web ve manuel kaynakları PostgreSQL ile ChromaDB'ye senkronize eder."

    def handle(self, *args, **options):
        try:
            result = sync_deep()
        except Exception as e:
            status, _ = SyncStatus.objects.get_or_create(key="default")
            status.last_error = str(e)
            status.updated_at = timezone.now()
            status.save(update_fields=["last_error", "updated_at"])
            raise

        self.stdout.write(
            self.style.SUCCESS(
                "Veri senkronizasyonu tamamlandı. "
                f"Kaynak: {result['source_count']}, Chunk: {result['chunk_count']}"
            )
        )
