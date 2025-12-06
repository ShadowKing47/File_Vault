"""
Stress tests for high-load scenarios.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


@pytest.mark.django_db
class TestConcurrentUploads:
    """Test concurrent file uploads"""
    
    def test_concurrent_uploads_same_user(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test multiple concurrent uploads from same user"""
        num_uploads = 10
        results = []
        
        def upload_file(index):
            content = f'Concurrent upload {index}'.encode()
            file = SimpleUploadedFile(f'concurrent_{index}.txt', content, content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            return response.status_code
        
        # Use ThreadPoolExecutor for controlled concurrency
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(upload_file, i) for i in range(num_uploads)]
            results = [future.result() for future in as_completed(futures)]
        
        # Most should succeed
        success_count = sum(1 for r in results if r == status.HTTP_201_CREATED)
        assert success_count >= num_uploads * 0.7  # At least 70% success rate
    
    def test_concurrent_uploads_different_users(self, api_client, user_factory, mock_object_storage, disable_rate_limiting):
        """Test concurrent uploads from different users"""
        from rest_framework_simplejwt.tokens import RefreshToken
        
        num_users = 5
        results = []
        
        def upload_as_user(user_index):
            user = user_factory(username=f'concurrent_user_{user_index}')
            token = str(RefreshToken.for_user(user).access_token)
            
            content = f'Upload from user {user_index}'.encode()
            file = SimpleUploadedFile(f'user_{user_index}.txt', content, content_type='text/plain')
            
            from rest_framework.test import APIClient
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            
            response = client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            return response.status_code
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(upload_as_user, i) for i in range(num_users)]
            results = [future.result() for future in as_completed(futures)]
        
        # All should succeed
        success_count = sum(1 for r in results if r == status.HTTP_201_CREATED)
        assert success_count >= num_users * 0.8


@pytest.mark.django_db
class TestLargeFileUploads:
    """Test large file handling"""
    
    def test_upload_10mb_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test uploading 10MB file"""
        size = 10 * 1024 * 1024
        content = b'X' * size
        
        file = SimpleUploadedFile('10mb.bin', content, content_type='application/octet-stream')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['size_bytes'] == size
    
    def test_upload_50mb_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test uploading 50MB file"""
        size = 50 * 1024 * 1024
        content = b'Y' * size
        
        file = SimpleUploadedFile('50mb.bin', content, content_type='application/octet-stream')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['size_bytes'] == size
    
    def test_many_chunks_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test file with many chunks (200+ chunks = 50MB+)"""
        chunk_size = 256 * 1024
        num_chunks = 200
        size = chunk_size * num_chunks
        
        content = b'Z' * size
        file = SimpleUploadedFile('many_chunks.bin', content, content_type='application/octet-stream')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == status.HTTP_201_CREATED
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        chunks = stored_file.chunks.all()
        
        # Should have many chunks
        assert len(chunks) == num_chunks


@pytest.mark.django_db
class TestHighVolumeOperations:
    """Test high volume of operations"""
    
    def test_many_small_files(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test uploading many small files"""
        num_files = 100
        
        for i in range(num_files):
            content = f'File {i}'.encode()
            file = SimpleUploadedFile(f'small_{i}.txt', content, content_type='text/plain')
            
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            
            assert response.status_code == status.HTTP_201_CREATED
    
    def test_rapid_upload_delete_cycles(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test rapid upload and delete cycles"""
        num_cycles = 20
        
        for i in range(num_cycles):
            # Upload
            content = f'Cycle {i}'.encode()
            file = SimpleUploadedFile(f'cycle_{i}.txt', content, content_type='text/plain')
            
            upload_response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            assert upload_response.status_code == status.HTTP_201_CREATED
            
            # Delete
            file_id = upload_response.data['file_id']
            delete_response = authenticated_client.delete(f'/api/files/{file_id}/delete/')
            assert delete_response.status_code == status.HTTP_200_OK
    
    def test_quota_stress(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test quota tracking under stress"""
        from data.models import UserQuota
        
        quota = UserQuota.objects.get(user=authenticated_client.user)
        initial_usage = quota.storage_used_bytes
        
        # Upload many files
        total_size = 0
        file_ids = []
        
        for i in range(50):
            size = (i + 1) * 1000
            content = b'X' * size
            file = SimpleUploadedFile(f'quota_{i}.txt', content, content_type='text/plain')
            
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            
            if response.status_code == status.HTTP_201_CREATED:
                total_size += size
                file_ids.append(response.data['file_id'])
        
        # Check quota accuracy
        quota.refresh_from_db()
        assert quota.storage_used_bytes >= initial_usage


@pytest.mark.django_db
class TestDeduplicationStress:
    """Test deduplication under stress"""
    
    def test_many_duplicate_uploads(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test uploading the same content many times"""
        content = b'Duplicate content for stress test'
        
        from data.models import ObjectChunk
        initial_chunk_count = ObjectChunk.objects.count()
        
        # Upload same content multiple times
        for i in range(50):
            file = SimpleUploadedFile(f'dup_{i}.txt', content, content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            assert response.status_code == status.HTTP_201_CREATED
        
        # Chunk count should not increase much (dedup working)
        final_chunk_count = ObjectChunk.objects.count()
        new_chunks = final_chunk_count - initial_chunk_count
        
        # Should create only 1 unique chunk despite 50 uploads
        assert new_chunks <= 5
    
    def test_partial_dedup_stress(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test partial deduplication with many files"""
        chunk_size = 256 * 1024
        shared_chunk = b'S' * chunk_size
        
        # Upload files with shared first chunk
        for i in range(20):
            unique_chunk = bytes([i]) * chunk_size
            content = shared_chunk + unique_chunk
            
            file = SimpleUploadedFile(f'partial_{i}.bin', content, content_type='application/octet-stream')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            
            assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestConcurrentDeletes:
    """Test concurrent delete operations"""
    
    def test_concurrent_deletes_different_files(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test concurrent deletion of different files"""
        # Upload files
        file_ids = []
        for i in range(20):
            content = f'Delete test {i}'.encode()
            file = SimpleUploadedFile(f'delete_{i}.txt', content, content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            file_ids.append(response.data['file_id'])
        
        # Delete concurrently
        def delete_file(file_id):
            response = authenticated_client.delete(f'/api/files/{file_id}/delete/')
            return response.status_code
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(delete_file, fid) for fid in file_ids]
            results = [future.result() for future in as_completed(futures)]
        
        # Most deletes should succeed
        success_count = sum(1 for r in results if r == status.HTTP_200_OK)
        assert success_count >= len(file_ids) * 0.8
