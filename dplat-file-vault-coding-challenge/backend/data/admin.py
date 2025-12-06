from django.contrib import admin
from data.models import UserQuota, ObjectChunk, StoredFile, FileChunk, UserObjectRef


@admin.register(UserQuota)
class UserQuotaAdmin(admin.ModelAdmin):
    list_display = ('user', 'storage_used_mb', 'storage_limit_mb', 'remaining_mb', 'usage_percentage')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('storage_used_bytes',)
    
    def storage_used_mb(self, obj):
        return f"{obj.storage_used_bytes / (1024 * 1024):.2f} MB"
    storage_used_mb.short_description = 'Used'
    
    def storage_limit_mb(self, obj):
        return f"{obj.storage_limit_bytes / (1024 * 1024):.2f} MB"
    storage_limit_mb.short_description = 'Limit'
    
    def remaining_mb(self, obj):
        remaining = max(0, obj.storage_limit_bytes - obj.storage_used_bytes)
        return f"{remaining / (1024 * 1024):.2f} MB"
    remaining_mb.short_description = 'Remaining'
    
    def usage_percentage(self, obj):
        if obj.storage_limit_bytes == 0:
            return "0%"
        percentage = (obj.storage_used_bytes / obj.storage_limit_bytes) * 100
        return f"{percentage:.1f}%"
    usage_percentage.short_description = 'Usage %'


@admin.register(ObjectChunk)
class ObjectChunkAdmin(admin.ModelAdmin):
    list_display = ('checksum_short', 'size_kb', 'ref_count', 'storage_nodes_count', 'created_at')
    search_fields = ('checksum',)
    readonly_fields = ('checksum', 'size_bytes', 'ref_count', 'created_at', 'storage_nodes')
    list_filter = ('created_at',)
    ordering = ('-created_at',)
    
    def checksum_short(self, obj):
        return f"{obj.checksum[:16]}..."
    checksum_short.short_description = 'Checksum'
    
    def size_kb(self, obj):
        return f"{obj.size_bytes / 1024:.2f} KB"
    size_kb.short_description = 'Size'
    
    def storage_nodes_count(self, obj):
        return len(obj.storage_nodes) if obj.storage_nodes else 0
    storage_nodes_count.short_description = 'Nodes'


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'owner', 'size_mb', 'chunks_count', 'created_at', 'modified_at')
    search_fields = ('filename', 'owner__username', 'file_checksum')
    list_filter = ('created_at', 'modified_at', 'owner')
    readonly_fields = ('file_checksum', 'created_at', 'modified_at')
    ordering = ('-created_at',)
    
    def size_mb(self, obj):
        return f"{obj.size_bytes / (1024 * 1024):.2f} MB"
    size_mb.short_description = 'Size'
    
    def chunks_count(self, obj):
        return obj.chunks.count()
    chunks_count.short_description = 'Chunks'


@admin.register(FileChunk)
class FileChunkAdmin(admin.ModelAdmin):
    list_display = ('file', 'sequence_no', 'chunk_checksum', 'chunk_size')
    search_fields = ('file__filename', 'chunk__checksum')
    list_filter = ('file__owner',)
    readonly_fields = ('file', 'chunk', 'sequence_no')
    ordering = ('file', 'sequence_no')
    
    def chunk_checksum(self, obj):
        return f"{obj.chunk.checksum[:16]}..."
    chunk_checksum.short_description = 'Chunk'
    
    def chunk_size(self, obj):
        return f"{obj.chunk.size_bytes / 1024:.2f} KB"
    chunk_size.short_description = 'Size'


@admin.register(UserObjectRef)
class UserObjectRefAdmin(admin.ModelAdmin):
    list_display = ('user', 'chunk_checksum', 'chunk_size', 'ref_count')
    search_fields = ('user__username', 'chunk__checksum')
    list_filter = ('user',)
    readonly_fields = ('user', 'chunk')
    
    def chunk_checksum(self, obj):
        return f"{obj.chunk.checksum[:16]}..."
    chunk_checksum.short_description = 'Chunk'
    
    def chunk_size(self, obj):
        return f"{obj.chunk.size_bytes / 1024:.2f} KB"
    chunk_size.short_description = 'Size'
    
    def ref_count(self, obj):
        return obj.chunk.ref_count
    ref_count.short_description = 'Refs'
