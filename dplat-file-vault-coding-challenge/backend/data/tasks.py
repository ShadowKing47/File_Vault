"""
Celery tasks for distributed file storage system.

Tasks:
- Replication: Ensure chunks are properly replicated across storage nodes
- Garbage Collection: Remove orphaned chunks with zero references
- Health Check: Monitor storage node availability and integrity
"""
import logging
import os
from typing import List, Dict, Any
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from data.models import ObjectChunk
from data.services.object_store import write_chunk, read_chunk, _chunk_path, NODES

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def replicate_chunk(self, chunk_id: int, target_replication_factor: int = 3) -> Dict[str, Any]:
    """
    Ensure a chunk is replicated to the target number of storage nodes.
    
    This task checks if a chunk exists on the expected number of nodes and
    replicates it to additional nodes if needed.
    
    Args:
        chunk_id: The ID of the ObjectChunk to replicate
        target_replication_factor: Target number of nodes (default: 3)
        
    Returns:
        Dict with replication status and details
    """
    try:
        chunk = ObjectChunk.objects.get(id=chunk_id)
        logger.info(
            "Starting chunk replication check",
            extra={
                "chunk_id": chunk_id,
                "checksum": chunk.checksum[:12],
                "current_nodes": len(chunk.storage_nodes),
                "target_nodes": target_replication_factor
            }
        )
        
        # Check which nodes actually have the chunk
        available_nodes = []
        for node in chunk.storage_nodes:
            path = _chunk_path(node, chunk.checksum)
            if os.path.exists(path):
                available_nodes.append(node)
        
        logger.debug(
            f"Found chunk on {len(available_nodes)}/{len(chunk.storage_nodes)} nodes",
            extra={"checksum": chunk.checksum[:12], "available_nodes": available_nodes}
        )
        
        # If we have enough replicas, we're done
        if len(available_nodes) >= target_replication_factor:
            return {
                "status": "ok",
                "chunk_id": chunk_id,
                "checksum": chunk.checksum[:12],
                "current_replicas": len(available_nodes),
                "target_replicas": target_replication_factor,
                "message": "Chunk already has sufficient replicas"
            }
        
        # Need to replicate to more nodes
        if len(available_nodes) == 0:
            logger.error(
                "Chunk not found on any node - cannot replicate",
                extra={"chunk_id": chunk_id, "checksum": chunk.checksum[:12]}
            )
            return {
                "status": "error",
                "chunk_id": chunk_id,
                "checksum": chunk.checksum[:12],
                "message": "Chunk not found on any storage node"
            }
        
        # Read chunk data from one of the available nodes
        data = read_chunk(chunk.checksum, available_nodes)
        
        # Select additional nodes for replication
        needed_nodes = target_replication_factor - len(available_nodes)
        available_for_replication = [n for n in NODES if n not in available_nodes]
        
        if len(available_for_replication) < needed_nodes:
            logger.warning(
                "Not enough nodes available for full replication",
                extra={
                    "chunk_id": chunk_id,
                    "needed": needed_nodes,
                    "available": len(available_for_replication)
                }
            )
            needed_nodes = len(available_for_replication)
        
        import random
        new_nodes = random.sample(available_for_replication, needed_nodes)
        
        # Write chunk to new nodes
        write_chunk(chunk.checksum, data, new_nodes)
        
        # Update chunk's storage_nodes list
        updated_nodes = list(set(available_nodes + new_nodes))
        chunk.storage_nodes = updated_nodes
        chunk.save(update_fields=["storage_nodes"])
        
        logger.info(
            "Chunk replication completed",
            extra={
                "chunk_id": chunk_id,
                "checksum": chunk.checksum[:12],
                "old_replicas": len(available_nodes),
                "new_replicas": len(updated_nodes),
                "added_nodes": new_nodes
            }
        )
        
        return {
            "status": "replicated",
            "chunk_id": chunk_id,
            "checksum": chunk.checksum[:12],
            "previous_replicas": len(available_nodes),
            "current_replicas": len(updated_nodes),
            "added_nodes": new_nodes
        }
        
    except ObjectChunk.DoesNotExist:
        logger.error(f"Chunk {chunk_id} not found in database")
        return {
            "status": "error",
            "chunk_id": chunk_id,
            "message": "Chunk not found in database"
        }
    except Exception as e:
        logger.exception(
            "Error during chunk replication",
            extra={"chunk_id": chunk_id}
        )
        # Retry the task
        raise self.retry(exc=e)


@shared_task
def check_all_chunk_replication(target_replication_factor: int = 3) -> Dict[str, Any]:
    """
    Check replication status for all chunks and queue replication tasks.
    
    This task scans all ObjectChunks and schedules replication tasks for
    chunks that don't have the target number of replicas.
    
    Args:
        target_replication_factor: Target number of nodes (default: 3)
        
    Returns:
        Dict with scan results and number of replication tasks queued
    """
    logger.info("Starting full replication check")
    
    chunks_needing_replication = []
    total_chunks = 0
    
    for chunk in ObjectChunk.objects.all():
        total_chunks += 1
        
        # Count actual files on disk
        available_count = sum(
            1 for node in chunk.storage_nodes
            if os.path.exists(_chunk_path(node, chunk.checksum))
        )
        
        if available_count < target_replication_factor:
            chunks_needing_replication.append(chunk.id)
            # Queue replication task
            replicate_chunk.delay(chunk.id, target_replication_factor)
    
    logger.info(
        "Replication check completed",
        extra={
            "total_chunks": total_chunks,
            "chunks_needing_replication": len(chunks_needing_replication)
        }
    )
    
    return {
        "status": "completed",
        "total_chunks": total_chunks,
        "chunks_needing_replication": len(chunks_needing_replication),
        "replication_tasks_queued": len(chunks_needing_replication)
    }


@shared_task(bind=True, max_retries=2)
def garbage_collect_orphaned_chunks(self, batch_size: int = 100) -> Dict[str, Any]:
    """
    Remove chunks with zero references from database and storage nodes.
    
    This task finds ObjectChunks with ref_count <= 0 and removes them
    from both the database and physical storage.
    
    Args:
        batch_size: Number of chunks to process in one batch (default: 100)
        
    Returns:
        Dict with garbage collection statistics
    """
    try:
        logger.info("Starting garbage collection for orphaned chunks")
        
        # Find orphaned chunks
        orphaned_chunks = ObjectChunk.objects.filter(
            Q(ref_count__lte=0)
        )[:batch_size]
        
        orphaned_count = orphaned_chunks.count()
        
        if orphaned_count == 0:
            logger.info("No orphaned chunks found")
            return {
                "status": "completed",
                "chunks_deleted": 0,
                "message": "No orphaned chunks to clean up"
            }
        
        deleted_count = 0
        errors = []
        
        for chunk in orphaned_chunks:
            try:
                logger.debug(
                    "Deleting orphaned chunk",
                    extra={"checksum": chunk.checksum[:12], "ref_count": chunk.ref_count}
                )
                
                # Delete physical files
                for node in chunk.storage_nodes:
                    path = _chunk_path(node, chunk.checksum)
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                            logger.debug(
                                f"Deleted chunk file from node",
                                extra={"checksum": chunk.checksum[:12], "node": node}
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete chunk file from node",
                            extra={
                                "checksum": chunk.checksum[:12],
                                "node": node,
                                "error": str(e)
                            }
                        )
                
                # Delete database record
                chunk.delete()
                deleted_count += 1
                
            except Exception as e:
                error_msg = f"Error deleting chunk {chunk.checksum[:12]}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        logger.info(
            "Garbage collection completed",
            extra={
                "orphaned_found": orphaned_count,
                "chunks_deleted": deleted_count,
                "errors": len(errors)
            }
        )
        
        return {
            "status": "completed",
            "orphaned_found": orphaned_count,
            "chunks_deleted": deleted_count,
            "errors": errors if errors else None
        }
        
    except Exception as e:
        logger.exception("Error during garbage collection")
        raise self.retry(exc=e)


@shared_task
def storage_node_health_check() -> Dict[str, Any]:
    """
    Check the health and availability of all storage nodes.
    
    This task verifies:
    - Node directories are accessible
    - Nodes are writable
    - Disk space is available
    - Sample chunks can be read
    
    Returns:
        Dict with health status for all nodes
    """
    logger.info("Starting storage node health check")
    
    health_status = {
        "timestamp": timezone.now().isoformat(),
        "nodes": {},
        "healthy_count": 0,
        "unhealthy_count": 0,
        "total_nodes": len(NODES)
    }
    
    for node in NODES:
        node_status = {
            "path": node,
            "accessible": False,
            "writable": False,
            "disk_space_mb": None,
            "chunk_count": 0,
            "errors": []
        }
        
        try:
            # Check if node directory exists and is accessible
            node_path = Path(node)
            if not node_path.exists():
                node_status["errors"].append("Directory does not exist")
                logger.warning(f"Storage node directory does not exist: {node}")
            else:
                node_status["accessible"] = True
                
                # Check if writable
                test_file = node_path / ".health_check"
                try:
                    test_file.write_text("health check")
                    test_file.unlink()
                    node_status["writable"] = True
                except Exception as e:
                    node_status["errors"].append(f"Not writable: {str(e)}")
                    logger.warning(f"Storage node not writable: {node} - {str(e)}")
                
                # Check disk space
                try:
                    import shutil
                    stat = shutil.disk_usage(node)
                    node_status["disk_space_mb"] = stat.free // (1024 * 1024)
                    
                    # Warn if less than 1GB free
                    if stat.free < 1024 * 1024 * 1024:
                        node_status["errors"].append(f"Low disk space: {node_status['disk_space_mb']}MB")
                        logger.warning(
                            f"Low disk space on storage node",
                            extra={"node": node, "free_mb": node_status['disk_space_mb']}
                        )
                except Exception as e:
                    node_status["errors"].append(f"Could not check disk space: {str(e)}")
                
                # Count chunks stored on this node
                try:
                    chunk_count = 0
                    for root, dirs, files in os.walk(node):
                        chunk_count += len([f for f in files if f != '.health_check'])
                    node_status["chunk_count"] = chunk_count
                except Exception as e:
                    node_status["errors"].append(f"Could not count chunks: {str(e)}")
        
        except Exception as e:
            node_status["errors"].append(f"Unexpected error: {str(e)}")
            logger.exception(f"Unexpected error checking storage node: {node}")
        
        # Determine if node is healthy
        is_healthy = (
            node_status["accessible"] and
            node_status["writable"] and
            len(node_status["errors"]) == 0
        )
        
        if is_healthy:
            health_status["healthy_count"] += 1
        else:
            health_status["unhealthy_count"] += 1
        
        node_status["healthy"] = is_healthy
        health_status["nodes"][node] = node_status
    
    logger.info(
        "Storage node health check completed",
        extra={
            "total_nodes": health_status["total_nodes"],
            "healthy": health_status["healthy_count"],
            "unhealthy": health_status["unhealthy_count"]
        }
    )
    
    return health_status


@shared_task
def verify_chunk_integrity(chunk_id: int) -> Dict[str, Any]:
    """
    Verify the integrity of a chunk across all its storage nodes.
    
    Checks that:
    - The chunk exists on all listed nodes
    - The data matches the expected checksum
    - All replicas are identical
    
    Args:
        chunk_id: The ID of the ObjectChunk to verify
        
    Returns:
        Dict with integrity check results
    """
    try:
        chunk = ObjectChunk.objects.get(id=chunk_id)
        logger.info(
            "Starting chunk integrity verification",
            extra={"chunk_id": chunk_id, "checksum": chunk.checksum[:12]}
        )
        
        results = {
            "chunk_id": chunk_id,
            "checksum": chunk.checksum[:12],
            "expected_nodes": len(chunk.storage_nodes),
            "verified_nodes": 0,
            "missing_nodes": [],
            "corrupted_nodes": [],
            "status": "ok"
        }
        
        reference_data = None
        
        for node in chunk.storage_nodes:
            path = _chunk_path(node, chunk.checksum)
            
            if not os.path.exists(path):
                results["missing_nodes"].append(node)
                logger.warning(
                    "Chunk missing from node",
                    extra={"checksum": chunk.checksum[:12], "node": node}
                )
                continue
            
            try:
                with open(path, "rb") as f:
                    data = f.read()
                
                # Verify checksum
                import hashlib
                actual_checksum = hashlib.sha256(data).hexdigest()
                
                if actual_checksum != chunk.checksum:
                    results["corrupted_nodes"].append(node)
                    logger.error(
                        "Chunk corrupted on node - checksum mismatch",
                        extra={
                            "checksum": chunk.checksum[:12],
                            "node": node,
                            "expected": chunk.checksum,
                            "actual": actual_checksum
                        }
                    )
                    continue
                
                # Verify consistency across nodes
                if reference_data is None:
                    reference_data = data
                elif data != reference_data:
                    results["corrupted_nodes"].append(node)
                    logger.error(
                        "Chunk data inconsistent across nodes",
                        extra={"checksum": chunk.checksum[:12], "node": node}
                    )
                    continue
                
                results["verified_nodes"] += 1
                
            except Exception as e:
                logger.error(
                    "Error reading chunk from node",
                    extra={
                        "checksum": chunk.checksum[:12],
                        "node": node,
                        "error": str(e)
                    }
                )
                results["corrupted_nodes"].append(node)
        
        # Determine overall status
        if results["missing_nodes"] or results["corrupted_nodes"]:
            results["status"] = "degraded"
        
        if results["verified_nodes"] == 0:
            results["status"] = "failed"
        
        logger.info(
            "Chunk integrity verification completed",
            extra={
                "chunk_id": chunk_id,
                "status": results["status"],
                "verified": results["verified_nodes"],
                "missing": len(results["missing_nodes"]),
                "corrupted": len(results["corrupted_nodes"])
            }
        )
        
        return results
        
    except ObjectChunk.DoesNotExist:
        logger.error(f"Chunk {chunk_id} not found in database")
        return {
            "status": "error",
            "chunk_id": chunk_id,
            "message": "Chunk not found in database"
        }
    except Exception as e:
        logger.exception(f"Error during chunk integrity verification for chunk {chunk_id}")
        return {
            "status": "error",
            "chunk_id": chunk_id,
            "message": str(e)
        }
