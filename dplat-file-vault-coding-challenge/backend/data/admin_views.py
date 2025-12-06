"""
API views for Celery task monitoring and storage system health.
"""
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from data.tasks import (
    check_all_chunk_replication,
    garbage_collect_orphaned_chunks,
    storage_node_health_check,
    replicate_chunk,
    verify_chunk_integrity
)
from data.models import ObjectChunk
from data.services.rate_limiter import sliding_window

logger = logging.getLogger(__name__)


def error_response(message, status_code=status.HTTP_400_BAD_REQUEST, **extra_data):
    """Unified error response format"""
    response_data = {"error": message}
    response_data.update(extra_data)
    return Response(response_data, status=status_code)


class StorageHealthView(APIView):
    """Get storage node health status"""
    permission_classes = [permissions.IsAdminUser]

    @sliding_window(limit=20, window_sec=60)
    def get(self, request):
        """Get current storage node health status"""
        logger.info("Storage health check requested", extra={"user_id": request.user.id})
        
        try:
            health_status = storage_node_health_check()
            return Response(health_status, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Error during storage health check")
            return error_response(
                "Failed to check storage health",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )


class ReplicationStatusView(APIView):
    """Check and manage chunk replication"""
    permission_classes = [permissions.IsAdminUser]

    @sliding_window(limit=20, window_sec=60)
    def get(self, request):
        """Get replication status summary"""
        logger.info("Replication status check requested", extra={"user_id": request.user.id})
        
        try:
            total_chunks = ObjectChunk.objects.count()
            chunks_with_refs = ObjectChunk.objects.filter(ref_count__gt=0).count()
            orphaned_chunks = ObjectChunk.objects.filter(ref_count__lte=0).count()
            
            return Response({
                "total_chunks": total_chunks,
                "active_chunks": chunks_with_refs,
                "orphaned_chunks": orphaned_chunks,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Error getting replication status")
            return error_response(
                "Failed to get replication status",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @sliding_window(limit=5, window_sec=300)
    def post(self, request):
        """Trigger replication check for all chunks"""
        logger.info("Replication check triggered", extra={"user_id": request.user.id})
        
        try:
            result = check_all_chunk_replication.delay()
            
            return Response({
                "message": "Replication check queued",
                "task_id": result.id
            }, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            logger.exception("Error triggering replication check")
            return error_response(
                "Failed to trigger replication check",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )


class GarbageCollectionView(APIView):
    """Trigger and monitor garbage collection"""
    permission_classes = [permissions.IsAdminUser]

    @sliding_window(limit=5, window_sec=300)
    def post(self, request):
        """Trigger garbage collection for orphaned chunks"""
        logger.info("Garbage collection triggered", extra={"user_id": request.user.id})
        
        batch_size = request.data.get('batch_size', 100)
        
        try:
            result = garbage_collect_orphaned_chunks.delay(batch_size=batch_size)
            
            return Response({
                "message": "Garbage collection queued",
                "task_id": result.id,
                "batch_size": batch_size
            }, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            logger.exception("Error triggering garbage collection")
            return error_response(
                "Failed to trigger garbage collection",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )


class ChunkIntegrityView(APIView):
    """Verify chunk integrity across storage nodes"""
    permission_classes = [permissions.IsAdminUser]

    @sliding_window(limit=10, window_sec=60)
    def post(self, request):
        """Verify integrity of a specific chunk"""
        chunk_id = request.data.get('chunk_id')
        
        if not chunk_id:
            return error_response("chunk_id is required", status.HTTP_400_BAD_REQUEST)
        
        logger.info(
            "Chunk integrity verification requested",
            extra={"user_id": request.user.id, "chunk_id": chunk_id}
        )
        
        try:
            result = verify_chunk_integrity.delay(chunk_id)
            
            return Response({
                "message": "Integrity verification queued",
                "task_id": result.id,
                "chunk_id": chunk_id
            }, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            logger.exception("Error triggering integrity verification")
            return error_response(
                "Failed to trigger integrity verification",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
