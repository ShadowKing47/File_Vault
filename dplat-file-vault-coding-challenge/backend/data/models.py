from django.conf import settings
from django.db import models


class UserQuota(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quota",
    )

    storage_limit_bytes = models.BigIntegerField(default=5 * 1024 * 1024 * 1024)  # 5GB
    storage_used_bytes = models.BigIntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} quota"


class ObjectChunk(models.Model):
    checksum = models.CharField(max_length=64, unique=True, db_index=True)
    size_bytes = models.BigIntegerField()
    ref_count = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    storage_nodes = models.JSONField(default=list)

    def __str__(self):
        return f"Chunk {self.checksum[:12]}..."


class StoredFile(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="files",
    )

    filename = models.CharField(max_length=255, db_index=True)
    size_bytes = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    file_checksum = models.CharField(max_length=64, blank=True, null=True)

    def __str__(self):
        return f"{self.owner.username}/{self.filename}"


class FileChunk(models.Model):
    file = models.ForeignKey(
        StoredFile,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk = models.ForeignKey(
        ObjectChunk,
        on_delete=models.CASCADE,
        related_name="file_links",
    )

    sequence_no = models.IntegerField()

    class Meta:
        unique_together = ("file", "sequence_no")
        ordering = ["sequence_no"]

    def __str__(self):
        return f"{self.file.filename} chunk #{self.sequence_no}"


class UserObjectRef(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chunk_refs",
    )

    chunk = models.ForeignKey(
        ObjectChunk,
        on_delete=models.CASCADE,
        related_name="user_refs",
    )

    class Meta:
        unique_together = ("user", "chunk")

    def __str__(self):
        return f"{self.user.username} ↔ {self.chunk.checksum[:12]}..."
