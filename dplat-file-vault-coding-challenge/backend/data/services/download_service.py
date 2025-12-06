"""
Service for handling file downloads with streaming support.
"""
import logging
from typing import Iterator
from data.models import StoredFile, FileChunk
from data.services.object_store import read_chunk

logger = logging.getLogger(__name__)


def get_file_for_download(user, file_id: int) -> StoredFile:
    """
    Retrieve a file for download, ensuring user has access.
    
    Args:
        user: The requesting user
        file_id: ID of the file to download
        
    Returns:
        StoredFile instance
        
    Raises:
        FileNotFoundError: If file doesn't exist or user doesn't have access
    """
    try:
        stored_file = StoredFile.objects.get(id=file_id, owner=user)
        logger.info(
            "File retrieved for download",
            extra={
                "user_id": user.id,
                "file_id": file_id,
                "file_name": stored_file.filename,
                "size_bytes": stored_file.size_bytes
            }
        )
        return stored_file
    except StoredFile.DoesNotExist:
        logger.warning(
            "File not found or access denied",
            extra={"user_id": user.id, "file_id": file_id}
        )
        raise FileNotFoundError(f"File {file_id} not found or access denied")


def stream_file_chunks(stored_file: StoredFile) -> Iterator[bytes]:
    """
    Stream file chunks in correct order for download.
    
    Args:
        stored_file: The file to stream
        
    Yields:
        bytes: Chunk data in sequence
    """
    logger.info(
        "Starting file stream",
        extra={
            "file_id": stored_file.id,
            "filename": stored_file.filename,
            "size_bytes": stored_file.size_bytes
        }
    )
    
    # Get all chunks in sequence order
    file_chunks = FileChunk.objects.filter(file=stored_file).select_related('chunk').order_by('sequence_no')
    
    total_chunks = file_chunks.count()
    logger.debug(f"Streaming {total_chunks} chunks", extra={"file_id": stored_file.id})
    
    for idx, file_chunk in enumerate(file_chunks):
        try:
            # Read chunk data from storage nodes
            chunk_data = read_chunk(file_chunk.chunk.checksum, file_chunk.chunk.storage_nodes)
            
            logger.debug(
                f"Chunk {idx + 1}/{total_chunks} streamed",
                extra={
                    "file_id": stored_file.id,
                    "chunk_checksum": file_chunk.chunk.checksum[:12],
                    "chunk_size": len(chunk_data)
                }
            )
            
            yield chunk_data
            
        except Exception as e:
            logger.error(
                "Failed to read chunk during streaming",
                extra={
                    "file_id": stored_file.id,
                    "chunk_checksum": file_chunk.chunk.checksum[:12],
                    "sequence_no": file_chunk.sequence_no,
                    "error": str(e)
                }
            )
            raise
    
    logger.info(
        "File streaming completed",
        extra={"file_id": stored_file.id, "chunks_streamed": total_chunks}
    )
