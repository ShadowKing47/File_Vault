from django.contrib import admin
from files.models import File


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'file_type', 'size_mb', 'uploaded_at')
    search_fields = ('original_filename', 'file_type')
    list_filter = ('uploaded_at', 'file_type')
    readonly_fields = ('id', 'uploaded_at')
    ordering = ('-uploaded_at',)
    
    def size_mb(self, obj):
        return f"{obj.size / (1024 * 1024):.2f} MB"
    size_mb.short_description = 'Size'
