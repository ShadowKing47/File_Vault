import logging
from typing import List, Tuple

from django.db import transaction
from django.conf import settings

from data.models import StoredFile, ObjectChunk, FileChunk, UserObjectRef
from data.services.chunking import iter_file_chunks, compute_full_file_hash
from data.services.quota import increase_quota_for_new_chunk_ref, QuotaExceededError
from data.services.object_store import choose_storage_nodes, write_chunk

logger = logging.getLogger(__name__)

@transaction.atomic
def handle_file_upload(user, uploaded_file) -> StoredFile:
    """Handle file upload with chunking, deduplication, and quota management"""
    try:
        logger.info(
            "Starting file upload processing",
            extra={"user_id": user.id, "file_name": uploaded_file.name}
        )

        file_checksum = compute_full_file_hash(uploaded_file)

        stored_file = StoredFile.objects.create(
            owner=user,
            filename=uploaded_file.name,
            size_bytes=uploaded_file.size,
            file_checksum=file_checksum,
        )

        uploaded_file.seek(0)

        sequence_no = 0
        for data, chunk_hash in iter_file_chunks(uploaded_file):
            chunk, created = ObjectChunk.objects.get_or_create(
                checksum=chunk_hash,
                defaults={
                    "size_bytes": len(data),
                    "ref_count": 0,
                },
            )

            if created:
                nodes = choose_storage_nodes(replication_factor=3)
                chunk.storage_nodes = nodes
                chunk.ref_count = 1
                chunk.save(update_fields=["storage_nodes", "ref_count"])

                write_chunk(chunk_hash, data, nodes)
                logger.debug(
                    "New chunk created and written to storage",
                    extra={"chunk_hash": chunk_hash[:12], "nodes": nodes}
                )
            else:
                chunk.ref_count += 1
                chunk.save(update_fields=["ref_count"])
                logger.debug(
                    "Existing chunk reused",
                    extra={"chunk_hash": chunk_hash[:12], "ref_count": chunk.ref_count}
                )

            increase_quota_for_new_chunk_ref(user, chunk)
            UserObjectRef.objects.get_or_create(
                user=user,
                chunk=chunk,
            )

            FileChunk.objects.create(
                file=stored_file,
                chunk=chunk,
                sequence_no=sequence_no,
            )
            sequence_no += 1

        logger.info(
            "File upload processing completed",
            extra={
                "user_id": user.id,
                "file_id": stored_file.id,
                "chunks_count": sequence_no
            }
        )
        
        # Trigger async replication verification for new chunks
        try:
            from data.tasks import replicate_chunk
            # Queue replication check for all chunks in this file (async)
            file_chunks = FileChunk.objects.filter(file=stored_file).select_related('chunk')
            for fc in file_chunks:
                replicate_chunk.apply_async(
                    args=[fc.chunk.id, 3],
                    countdown=60  # Check replication after 1 minute
                )
            logger.debug(
                f"Queued replication verification for {sequence_no} chunks",
                extra={"file_id": stored_file.id}
            )
        except Exception as e:
            # Don't fail the upload if replication task queueing fails
            logger.warning(
                "Failed to queue replication verification tasks",
                extra={"file_id": stored_file.id, "error": str(e)}
            )
        
        return stored_file

    except Exception as e:
        logger.exception(
            "Error during file upload processing",
            extra={"user_id": user.id, "file_name": uploaded_file.name}
        )
        raise    
