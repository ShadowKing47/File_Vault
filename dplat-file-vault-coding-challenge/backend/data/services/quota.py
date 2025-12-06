import logging
from dataclasses import dataclass
from django.db import transaction
from data.models import UserQuota, ObjectChunk, UserObjectRef

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Exception raised when user storage quota is exceeded"""
    pass


@dataclass
class QuotaStatus:
    """User quota status information"""
    limit: int
    used: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def get_or_create_user_quota(user) -> UserQuota:
    """Get or create user quota object"""
    quota, created = UserQuota.objects.get_or_create(user=user)
    if created:
        logger.info("New user quota created", extra={"user_id": user.id})
    return quota


def get_quota_status(user) -> QuotaStatus:
    """Get current quota status for user"""
    quota = get_or_create_user_quota(user)
    return QuotaStatus(limit=quota.storage_limit_bytes, used=quota.storage_used_bytes)


@transaction.atomic
def increase_quota_for_new_chunk_ref(user, chunk: ObjectChunk):
    """Increase user quota when referencing a new chunk"""
    quota = get_or_create_user_quota(user)

    already_ref = UserObjectRef.objects.filter(user=user, chunk=chunk).exists()
    if not already_ref:
        new_used = quota.storage_used_bytes + chunk.size_bytes
        if new_used > quota.storage_limit_bytes:
            logger.warning(
                "Quota exceeded",
                extra={
                    "user_id": user.id,
                    "current_used": quota.storage_used_bytes,
                    "chunk_size": chunk.size_bytes,
                    "limit": quota.storage_limit_bytes
                }
            )
            raise QuotaExceededError("User storage quota exceeded")
        quota.storage_used_bytes = new_used
        quota.save(update_fields=["storage_used_bytes"])
        logger.debug(
            "Quota increased",
            extra={"user_id": user.id, "new_used": new_used, "chunk_size": chunk.size_bytes}
        )


@transaction.atomic
def decrease_quota_for_chunk_ref(user, chunk: ObjectChunk):
    """Decrease user quota when dereferencing a chunk"""
    quota = get_or_create_user_quota(user)
    still_refs = UserObjectRef.objects.filter(user=user, chunk=chunk).exists()
    if not still_refs:
        return

    if UserObjectRef.objects.filter(user=user, chunk=chunk).count() == 1:
        old_used = quota.storage_used_bytes
        quota.storage_used_bytes = max(0, quota.storage_used_bytes - chunk.size_bytes)
        quota.save(update_fields=["storage_used_bytes"])
        logger.debug(
            "Quota decreased",
            extra={
                "user_id": user.id,
                "old_used": old_used,
                "new_used": quota.storage_used_bytes,
                "chunk_size": chunk.size_bytes
            }
        )


