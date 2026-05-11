from django.contrib import admin, messages

from .models import ChatMessage, SyncStatus, UniversityContent, UniversityLink, UniversityPDF
from .vector_store import delete_source_content, upsert_content


@admin.action(description="Seçili kaynakları ChromaDB'ye yeniden indeksle")
def reindex_selected_content(modeladmin, request, queryset):
    success_count = 0
    failure_count = 0

    for content in queryset:
        try:
            upsert_content(content.source_name, content.raw_text)
            success_count += 1
        except Exception:
            failure_count += 1
            modeladmin.message_user(
                request,
                f"'{content.source_name}' yeniden indekslenirken hata oluştu. Logları kontrol edin.",
                level=messages.ERROR,
            )

    if success_count:
        modeladmin.message_user(
            request,
            f"{success_count} kaynak ChromaDB'ye yeniden indekslendi.",
            level=messages.SUCCESS,
        )
    if failure_count:
        modeladmin.message_user(
            request,
            f"{failure_count} kaynak yeniden indekslenemedi.",
            level=messages.WARNING,
        )


@admin.action(description="Seçili kaynakları DB ve ChromaDB'den birlikte sil")
def delete_selected_content_and_vectors(modeladmin, request, queryset):
    source_names = list(queryset.values_list("source_name", flat=True))
    deleted_vectors = 0
    failed_vectors = 0

    for source_name in source_names:
        try:
            delete_source_content(source_name)
            deleted_vectors += 1
        except Exception:
            failed_vectors += 1
            modeladmin.message_user(
                request,
                f"'{source_name}' için ChromaDB temizliği başarısız oldu. Logları kontrol edin.",
                level=messages.ERROR,
            )

    deleted_count, _ = queryset.delete()
    modeladmin.message_user(
        request,
        f"{deleted_count} DB kaydı silindi; {deleted_vectors} kaynak için ChromaDB temizliği yapıldı.",
        level=messages.SUCCESS if failed_vectors == 0 else messages.WARNING,
    )


@admin.register(UniversityContent)
class UniversityContentAdmin(admin.ModelAdmin):
    list_display = ("source_name", "text_length", "last_updated")
    list_filter = ("last_updated",)
    search_fields = ("source_name", "raw_text")
    readonly_fields = ("last_updated", "text_length")
    ordering = ("source_name",)
    actions = (reindex_selected_content, delete_selected_content_and_vectors)

    @admin.display(description="Metin Uzunluğu")
    def text_length(self, obj):
        return len(obj.raw_text or "")

    def delete_model(self, request, obj):
        delete_source_content(obj.source_name)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for source_name in queryset.values_list("source_name", flat=True):
            delete_source_content(source_name)
        super().delete_queryset(request, queryset)


@admin.register(UniversityLink)
class UniversityLinkAdmin(admin.ModelAdmin):
    list_display = ("title", "url", "added_at")
    search_fields = ("title", "url")
    list_filter = ("added_at",)


@admin.register(UniversityPDF)
class UniversityPDFAdmin(admin.ModelAdmin):
    list_display = ("title", "file", "uploaded_at")
    search_fields = ("title", "file")
    list_filter = ("uploaded_at",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("short_user_message", "created_at")
    search_fields = ("user_message", "bot_response")
    list_filter = ("created_at",)
    readonly_fields = ("user_message", "bot_response", "created_at")

    @admin.display(description="Kullanıcı Mesajı")
    def short_user_message(self, obj):
        return obj.user_message[:80]


@admin.register(SyncStatus)
class SyncStatusAdmin(admin.ModelAdmin):
    list_display = ("key", "last_success_at", "source_count", "chunk_count", "has_error", "updated_at")
    readonly_fields = (
        "key",
        "last_started_at",
        "last_success_at",
        "source_count",
        "chunk_count",
        "last_error",
        "updated_at",
    )

    @admin.display(description="Hata Var mı", boolean=True)
    def has_error(self, obj):
        return bool(obj.last_error)
