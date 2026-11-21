from django.contrib import admin

from .models import FileRecord


@admin.register(FileRecord)
class FileRecordAdmin(admin.ModelAdmin):
    list_display = ["original_name", "file_type", "size", "uploaded_by", "created_at"]
    list_filter = ["file_type"]
    search_fields = ["original_name"]
    readonly_fields = ["stored_name", "mime_type", "size", "created_at", "updated_at"]
