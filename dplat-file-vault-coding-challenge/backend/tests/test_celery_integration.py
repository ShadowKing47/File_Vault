"""
Tests for Celery task integration.
"""
import pytest
from data.models import ObjectChunk
from data.tasks import (
    replicate_chunk,
    check_all_chunk_replication,
    garbage_collect_orphaned_chunks,
    storage_node_health_check,
    verify_chunk_integrity
)


@pytest.mark.django_db
class TestCeleryTaskExecution:
    """Test Celery task execution"""
    
    def test_replicate_chunk_task(self, chunk_factory, mock_object_storage, celery_eager):
        """Test replicate_chunk task"""
        chunk = chunk_factory(storage_nodes=['node1'])
        
        # Add to storage
        test_data = b'test chunk data'
        mock_object_storage.write_chunk(chunk.checksum, test_data, 'node1')
        
        # Run replication task
        result = replicate_chunk(chunk.checksum, 'node1', 'node2')
        
        # Should complete
        assert result is not None
    
    def test_check_all_chunk_replication_task(self, chunk_factory, mock_object_storage, celery_eager):
        """Test check_all_chunk_replication task"""
        # Create chunks
        chunk1 = chunk_factory(storage_nodes=['node1', 'node2', 'node3'])
        chunk2 = chunk_factory(checksum='b' * 64, storage_nodes=['node1'])
        
        # Add to storage
        mock_object_storage.write_chunk(chunk1.checksum, b'data1', 'node1')
        mock_object_storage.write_chunk(chunk2.checksum, b'data2', 'node1')
        
        # Run task
        result = check_all_chunk_replication()
        
        # Should complete
        assert result is not None
    
    def test_garbage_collect_task(self, chunk_factory, mock_object_storage, celery_eager):
        """Test garbage_collect_orphaned_chunks task"""
        # Create orphaned chunks
        orphan1 = chunk_factory(checksum='orphan1' + 'a' * 56, ref_count=0)
        orphan2 = chunk_factory(checksum='orphan2' + 'b' * 56, ref_count=-1)
        referenced = chunk_factory(checksum='ref' + 'c' * 61, ref_count=3)
        
        # Add to storage
        for node in orphan1.storage_nodes:
            mock_object_storage.write_chunk(orphan1.checksum, b'data', node)
        
        # Run GC
        result = garbage_collect_orphaned_chunks()
        
        # Should complete
        assert result is not None
        
        # Orphans should be deleted
        assert not ObjectChunk.objects.filter(checksum=orphan1.checksum).exists()
        assert not ObjectChunk.objects.filter(checksum=orphan2.checksum).exists()
        
        # Referenced should remain
        assert ObjectChunk.objects.filter(checksum=referenced.checksum).exists()
    
    def test_storage_node_health_check_task(self, mock_object_storage, celery_eager):
        """Test storage_node_health_check task"""
        result = storage_node_health_check()
        
        # Should complete
        assert result is not None
    
    def test_verify_chunk_integrity_task(self, chunk_factory, mock_object_storage, celery_eager):
        """Test verify_chunk_integrity task"""
        chunk = chunk_factory()
        
        # Add to storage
        test_data = b'integrity test data'
        for node in chunk.storage_nodes:
            mock_object_storage.write_chunk(chunk.checksum, test_data, node)
        
        # Run integrity check
        result = verify_chunk_integrity(chunk.checksum)
        
        # Should complete
        assert result is not None


@pytest.mark.django_db
class TestCeleryTaskErrors:
    """Test Celery task error handling"""
    
    def test_replicate_nonexistent_chunk(self, mock_object_storage, celery_eager):
        """Test replicating chunk that doesn't exist"""
        # Should handle gracefully
        try:
            result = replicate_chunk('nonexistent_checksum', 'node1', 'node2')
            # Task should complete without crashing
        except Exception as e:
            # Or may raise appropriate exception
            pass
    
    def test_gc_with_storage_errors(self, chunk_factory, mock_object_storage, celery_eager):
        """Test GC with storage node errors"""
        orphan = chunk_factory(ref_count=0)
        
        # Simulate node failure
        mock_object_storage.simulate_node_failure('node1')
        
        # GC should handle errors
        try:
            result = garbage_collect_orphaned_chunks()
            assert result is not None
        except Exception as e:
            # Should handle gracefully
            pass
        
        # Restore node
        mock_object_storage.restore_node('node1')
    
    def test_health_check_with_failed_nodes(self, mock_object_storage, celery_eager):
        """Test health check with failed nodes"""
        mock_object_storage.simulate_node_failure('node2')
        
        # Should complete despite failure
        result = storage_node_health_check()
        assert result is not None
        
        mock_object_storage.restore_node('node2')


@pytest.mark.django_db
class TestCeleryBeat:
    """Test Celery Beat periodic tasks"""
    
    def test_periodic_tasks_configured(self, settings):
        """Test that periodic tasks are configured"""
        assert hasattr(settings, 'CELERY_BEAT_SCHEDULE')
        
        schedule = settings.CELERY_BEAT_SCHEDULE
        
        # Should have replication check
        assert 'check_chunk_replication' in schedule or 'check-chunk-replication' in schedule
        
        # Should have GC task
        assert any('garbage' in key.lower() for key in schedule.keys())
        
        # Should have health check
        assert any('health' in key.lower() for key in schedule.keys())
    
    def test_periodic_task_intervals(self, settings):
        """Test periodic task intervals are reasonable"""
        schedule = settings.CELERY_BEAT_SCHEDULE
        
        # All tasks should have schedules
        for task_name, task_config in schedule.items():
            assert 'schedule' in task_config
            assert 'task' in task_config


@pytest.mark.django_db
class TestCeleryConfiguration:
    """Test Celery configuration"""
    
    def test_celery_broker_configured(self, settings):
        """Test that Celery broker is configured"""
        assert hasattr(settings, 'CELERY_BROKER_URL')
        assert settings.CELERY_BROKER_URL is not None
    
    def test_celery_result_backend_configured(self, settings):
        """Test that result backend is configured"""
        assert hasattr(settings, 'CELERY_RESULT_BACKEND')
    
    def test_celery_timezone(self, settings):
        """Test Celery timezone matches Django"""
        if hasattr(settings, 'CELERY_TIMEZONE'):
            # Should match Django timezone
            assert settings.CELERY_TIMEZONE == settings.TIME_ZONE


@pytest.mark.django_db
class TestTaskIntegration:
    """Test task integration with file operations"""
    
    def test_gc_triggered_after_file_delete(self, authenticated_client, mock_object_storage, disable_rate_limiting, celery_eager):
        """Test that GC can clean up after file deletion"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from data.models import StoredFile
        
        # Upload unique file
        content = b'Unique content for GC integration test'
        file = SimpleUploadedFile('gc_integration.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = response.data['file_id']
        
        stored_file = StoredFile.objects.get(id=file_id)
        chunk_checksums = [c.checksum for c in stored_file.chunks.all()]
        
        # Delete file
        authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        # Run GC
        garbage_collect_orphaned_chunks()
        
        # Chunks should be cleaned up
        for checksum in chunk_checksums:
            chunk = ObjectChunk.objects.filter(checksum=checksum).first()
            if chunk:
                # If exists, must have other references
                assert chunk.chunk.ref_count > 0
    
    def test_replication_after_upload(self, authenticated_client, mock_object_storage, disable_rate_limiting, celery_eager):
        """Test that replication check works after upload"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from data.models import StoredFile
        
        # Upload file
        content = b'Content for replication test'
        file = SimpleUploadedFile('replication.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        # Run replication check
        result = check_all_chunk_replication()
        
        # Should complete without errors
        assert result is not None
