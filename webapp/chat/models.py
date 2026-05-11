from django.db import models


class UniversityLink(models.Model):
    title = models.CharField(max_length=200, verbose_name="Sayfa Başlığı")
    url = models.URLField(verbose_name="Web Adresi (URL)")
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class UniversityPDF(models.Model):
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="pdfs/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class ChatMessage(models.Model):
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    user_message = models.TextField()
    bot_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Soru: {self.user_message[:20]}..."


# BOTUN ASIL OKUYACAĞI TEMİZLENMİŞ VERİ TABLOSU
class UniversityContent(models.Model):
    source_name = models.CharField(
        max_length=255, verbose_name="Kaynak Adı (PDF veya Link Adı)"
    )
    raw_text = models.TextField(verbose_name="Temizlenmiş Metin")
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.source_name


class SyncStatus(models.Model):
    key = models.CharField(max_length=50, unique=True, default="default")
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    source_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sync Durumu"
        verbose_name_plural = "Sync Durumları"

    def __str__(self):
        return f"SyncStatus({self.key})"
