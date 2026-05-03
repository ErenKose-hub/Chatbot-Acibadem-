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
    user_message = models.TextField()
    bot_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

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
