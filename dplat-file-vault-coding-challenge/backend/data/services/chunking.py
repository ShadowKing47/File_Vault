import logging
import hashlib
from django.conf import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = getattr(settings, "OBJECT_CHUNK_SIZE", 256 * 1024)  # 256KB default


def iter_file_chunks(uploaded_file, chunk_size: int = CHUNK_SIZE):
    """Iterate over file chunks and compute hash for each chunk"""
    while True:
        data = uploaded_file.read(chunk_size)
        if not data:
            break
        chunk_hash = hashlib.sha256(data).hexdigest()
        yield data, chunk_hash


def compute_full_file_hash(uploaded_file, chunk_size: int = CHUNK_SIZE) -> str:
    """Compute SHA256 hash of entire file"""
    uploaded_file.seek(0)
    hasher = hashlib.sha256()
    while True:
        data = uploaded_file.read(chunk_size)
        if not data:
            break
        hasher.update(data)
    uploaded_file.seek(0)
    file_hash = hasher.hexdigest()
    logger.debug("Computed file hash", extra={"hash": file_hash[:12]})
    return file_hash
