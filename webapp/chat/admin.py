from django.contrib import admin
from .models import UniversityPDF, UniversityLink, UniversityContent, ChatMessage

admin.site.register(UniversityPDF)
admin.site.register(UniversityLink)
admin.site.register(UniversityContent)
admin.site.register(ChatMessage)
