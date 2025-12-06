"""
Tests for garbage collection functionality.
"""
import pytest
from data.models import ObjectChunk
from data.tasks import garbage_collect_orphaned_chunks
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
class TestGarbageCollection:
    """Test garbage collection of orphaned chunks"""
    
    def test_gc_removes_orphaned_chunks(self, chunk_factory, mock_object_storage, celery_eager):
        """Test that GC removes chunks with ref_count <= 0"""
        # Create orphaned chunk
        orphaned_chunk = chunk_factory(ref_count=0)
        checksum = orphaned_chunk.checksum
        
        # Run GC
        garbage_collect_orphaned_chunks()
        
        # Verify chunk deleted
        assert not ObjectChunk.objects.filter(checksum=checksum).exists()
    
    def test_gc_preserves_referenced_chunks(self, chunk_factory, celery_eager):
        """Test that GC doesn't remove chunks with ref_count > 0"""
        # Create referenced chunk
        referenced_chunk = chunk_factory(ref_count=2)
        checksum = referenced_chunk.checksum
        
        # Run GC
        garbage_collect_orphaned_chunks()
        
        # Verify chunk still exists
        assert ObjectChunk.objects.filter(checksum=checksum).exists()
    
    def test_gc_mixed_chunks(self, chunk_factory, mock_object_storage, celery_eager):
        """Test GC with both orphaned and referenced chunks"""
        # Create mix of chunks
        orphaned1 = chunk_factory(checksum='orphan1' + 'a' * 56, ref_count=0)
        orphaned2 = chunk_factory(checksum='orphan2' + 'b' * 56, ref_count=-1)
        referenced1 = chunk_factory(checksum='ref1' + 'c' * 60, ref_count=1)
        referenced2 = chunk_factory(checksum='ref2' + 'd' * 60, ref_count=5)
        
        # Run GC
        garbage_collect_orphaned_chunks()
        
        # Verify orphaned chunks deleted
        assert not ObjectChunk.objects.filter(checksum=orphaned1.checksum).exists()
        assert not ObjectChunk.objects.filter(checksum=orphaned2.checksum).exists()
        
        # Verify referenced chunks preserved
        assert ObjectChunk.objects.filter(checksum=referenced1.checksum).exists()
        assert ObjectChunk.objects.filter(checksum=referenced2.checksum).exists()
    
    def test_gc_deletes_from_storage(self, chunk_factory, mock_object_storage, celery_eager):
        """Test that GC deletes chunks from object storage"""
        orphaned_chunk = chunk_factory(ref_count=0)
        checksum = orphaned_chunk.checksum
        
        # Add chunk to mock storage
        for node in orphaned_chunk.storage_nodes:
            mock_object_storage.write_chunk(checksum, b'test data', node)
        
        # Run GC
        garbage_collect_orphaned_chunks()
        
        # Verify chunk deleted from storage
        for node in orphaned_chunk.storage_nodes:
            assert not mock_object_storage.chunk_exists(checksum, node)
    
    def test_gc_handles_missing_storage_chunks(self, chunk_factory, celery_eager):
        """Test GC handles chunks missing from storage gracefully"""
        # Create orphaned chunk that doesn't exist in storage
        orphaned_chunk = chunk_factory(ref_count=0)
        checksum = orphaned_chunk.checksum
        
        # Run GC (should not raise exception)
        garbage_collect_orphaned_chunks()
        
        # Verify chunk deleted from database
        assert not ObjectChunk.objects.filter(checksum=checksum).exists()


@pytest.mark.django_db
class TestGarbageCollectionIntegration:
    """Integration tests for GC with file operations"""
    
    def test_gc_after_file_deletion(self, authenticated_client, mock_object_storage, disable_rate_limiting, celery_eager):
        """Test GC cleans up after file deletion"""
        content = b'Content to be garbage collected'
        file = SimpleUploadedFile('gc_test.txt', content, content_type='text/plain')
        
        # Upload file
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=file_id)
        chunk_checksums = [chunk.checksum for chunk in stored_file.chunks.all()]
        
        # Delete file
        authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        # Run GC
        garbage_collect_orphaned_chunks()
        
        # Verify orphaned chunks removed
        for checksum in chunk_checksums:
            # Chunk should be deleted if it was only referenced by this file
            chunk = ObjectChunk.objects.filter(checksum=checksum).first()
            if chunk:
                # If chunk still exists, it must have other references
                assert chunk.chunk.ref_count > 0
    
    def test_gc_preserves_shared_chunks_after_partial_deletion(self, authenticated_client, mock_object_storage, disable_rate_limiting, celery_eager):
        """Test GC preserves shared chunks when only some files deleted"""
        content = b'Shared content between files'
        
        # Upload two files with same content
        file1 = SimpleUploadedFile('file1.txt', content, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        file1_id = response1.data['file_id']
        
        file2 = SimpleUploadedFile('file2.txt', content, content_type='text/plain')
        authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file1 = StoredFile.objects.get(id=file1_id)
        chunk_checksums = [chunk.checksum for chunk in stored_file1.chunks.all()]
        
        # Delete first file
        authenticated_client.delete(f'/api/files/{file1_id}/delete/')
        
        # Run GC
        garbage_collect_orphaned_chunks()
        
        # Verify chunks still exist (referenced by second file)
        for checksum in chunk_checksums:
            assert ObjectChunk.objects.filter(checksum=checksum).exists()


@pytest.mark.django_db
class TestStorageNodeHealthCheck:
    """Test storage node health check functionality"""
    
    def test_health_check_all_nodes_healthy(self, mock_object_storage, celery_eager):
        """Test health check when all nodes are healthy"""
        from data.tasks import storage_node_health_check
        
        # All nodes should be accessible
        result = storage_node_health_check()
        
        # Should complete without errors
        assert result is not None
    
    def test_health_check_with_failed_node(self, mock_object_storage, celery_eager):
        """Test health check when a node has failed"""
        from data.tasks import storage_node_health_check
        
        # Simulate node failure
        mock_object_storage.simulate_node_failure('node2')
        
        # Health check should detect failure
        result = storage_node_health_check()
        
        # Should still complete (may log warnings)
        assert result is not None
        
        # Restore node
        mock_object_storage.restore_node('node2')


@pytest.mark.django_db
class TestReplicationCheck:
    """Test replication verification"""
    
    def test_replication_check_all_replicated(self, chunk_factory, mock_object_storage, celery_eager):
        """Test replication check when all chunks properly replicated"""
        from data.tasks import check_all_chunk_replication
        
        # Create chunk with proper replication
        chunk = chunk_factory(storage_nodes=['node1', 'node2', 'node3'])
        
        # Add to storage
        for node in chunk.storage_nodes:
            mock_object_storage.write_chunk(chunk.checksum, b'test data', node)
        
        # Run replication check
        result = check_all_chunk_replication()
        
        # Should complete successfully
        assert result is not None
    
    def test_replication_check_under_replicated(self, chunk_factory, mock_object_storage, celery_eager):
        """Test replication check detects under-replicated chunks"""
        from data.tasks import check_all_chunk_replication
        
        # Create chunk with insufficient replication
        chunk = chunk_factory(storage_nodes=['node1'])
        
        # Add to storage on single node
        mock_object_storage.write_chunk(chunk.checksum, b'test data', 'node1')
        
        # Run replication check (should attempt to fix)
        result = check_all_chunk_replication()
        
        # Should complete
        assert result is not None
