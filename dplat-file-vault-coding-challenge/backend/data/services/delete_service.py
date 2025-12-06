import logging
from django.db import transaction
from data.models import StoredFile, FileChunk, UserObjectRef, ObjectChunk
from data.services.quota import decrease_quota_for_chunk_ref
from data.services.object_store import delete_chunk

logger = logging.getLogger(__name__)


@transaction.atomic
def delete_file(user, file_id):
    """Delete a file and clean up associated chunks with reference counting"""
    try:
        stored_file = StoredFile.objects.get(id=file_id, owner=user)
        logger.info(
            "Starting file deletion",
            extra={"user_id": user.id, "file_id": file_id, "file_name": stored_file.filename}
        )
    except StoredFile.DoesNotExist:
        logger.warning(
            "File not found during deletion",
            extra={"user_id": user.id, "file_id": file_id}
        )
        raise FileNotFoundError("File not found or access denied")

    # Prefetch related chunks
    file_chunks = list(
        FileChunk.objects.filter(file=stored_file).select_related("chunk")
    )
    logger.debug(f"Processing {len(file_chunks)} chunks for deletion")

    chunks_deleted = 0
    for fc in file_chunks:
        chunk = fc.chunk

        # Remove user ↔ chunk logical link
        UserObjectRef.objects.filter(user=user, chunk=chunk).delete()

        # Adjust per-user quota if this was the last reference for the user
        decrease_quota_for_chunk_ref(user, chunk)

        # Decrease global chunk ref_count
        chunk.ref_count -= 1
        chunk.save(update_fields=["ref_count"])

        # If no one uses this chunk anymore, delete from object storage + DB
        if chunk.ref_count <= 0:
            try:
                delete_chunk(chunk.checksum, chunk.storage_nodes)
                chunk.delete()
                chunks_deleted += 1
                logger.debug(
                    "Chunk deleted from storage",
                    extra={"checksum": chunk.checksum[:12]}
                )
            except Exception as e:
                logger.error(
                    "Failed to delete chunk from storage",
                    extra={"checksum": chunk.checksum[:12], "error": str(e)}
                )

    # Finally delete the StoredFile record
    stored_file.delete()
    logger.info(
        "File deletion completed",
        extra={
            "user_id": user.id,
            "file_id": file_id,
            "chunks_deleted": chunks_deleted,
            "total_chunks": len(file_chunks)
        }
    )
    
    # Trigger async garbage collection to clean up any orphaned chunks
    try:
        from data.tasks import garbage_collect_orphaned_chunks
        # Run garbage collection after 5 minutes to catch any orphaned chunks
        garbage_collect_orphaned_chunks.apply_async(countdown=300)
        logger.debug("Queued garbage collection task after file deletion")
    except Exception as e:
        # Don't fail deletion if GC queueing fails
        logger.warning(
            "Failed to queue garbage collection task",
            extra={"error": str(e)}
        )
    
    return True
