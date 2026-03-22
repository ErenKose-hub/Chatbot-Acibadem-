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
