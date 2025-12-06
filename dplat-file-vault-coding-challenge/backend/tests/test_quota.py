"""
Tests for user quota management.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from data.models import UserQuota


@pytest.mark.django_db
class TestQuotaTracking:
    """Test quota tracking functionality"""
    
    def test_quota_created_on_user_registration(self, user_factory):
        """Test that quota is created when user registers"""
        user = user_factory()
        
        quota = UserQuota.objects.get(user=user)
        assert quota.storage_limit_bytes == 5 * 1024 * 1024 * 1024  # 5GB
        assert quota.storage_used_bytes == 0
    
    def test_quota_increases_on_upload(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that quota increases when files are uploaded"""
        quota = UserQuota.objects.get(user=authenticated_client.user)
        initial_usage = quota.storage_used_bytes
        
        content = b'X' * 10000
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == status.HTTP_201_CREATED
        
        quota.refresh_from_db()
        assert quota.storage_used_bytes == initial_usage + len(content)
    
    def test_quota_decreases_on_delete(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that quota decreases when files are deleted"""
        content = b'X' * 10000
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        
        # Upload file
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = response.data['file_id']
        
        quota = UserQuota.objects.get(user=authenticated_client.user)
        usage_after_upload = quota.storage_used_bytes
        
        # Delete file
        response = authenticated_client.delete(f'/api/files/{file_id}/delete/')
        assert response.status_code == status.HTTP_200_OK
        
        quota.refresh_from_db()
        assert quota.storage_used_bytes < usage_after_upload
    
    def test_quota_endpoint_returns_usage(self, authenticated_client, disable_rate_limiting):
        """Test quota endpoint returns current usage"""
        response = authenticated_client.get('/api/quota/')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'storage_used_bytes' in response.data
        assert 'storage_limit_bytes' in response.data
        assert 'storage_used_mb' in response.data
        assert 'storage_limit_mb' in response.data
    
    def test_shared_chunks_quota_handling(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that shared chunks are counted correctly in quota"""
        content = b'Shared content'
        
        # Upload first file
        file1 = SimpleUploadedFile('file1.txt', content, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        
        quota = UserQuota.objects.get(user=authenticated_client.user)
        usage_after_first = quota.storage_used_bytes
        
        # Upload identical file - should still count in quota
        file2 = SimpleUploadedFile('file2.txt', content, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        
        quota.refresh_from_db()
        # Both files count toward quota even though chunks are deduplicated
        assert quota.storage_used_bytes == usage_after_first + len(content)


@pytest.mark.django_db
class TestQuotaEnforcement:
    """Test quota enforcement"""
    
    def test_upload_exceeds_quota(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that upload fails when quota would be exceeded"""
        # Set quota to small value
        quota = UserQuota.objects.get(user=authenticated_client.user)
        quota.storage_limit_bytes = 1000
        quota.storage_used_bytes = 900
        quota.save()
        
        # Try to upload file that exceeds quota
        content = b'X' * 200
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'quota' in str(response.data).lower()
    
    def test_upload_at_quota_limit(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test upload that exactly reaches quota limit"""
        quota = UserQuota.objects.get(user=authenticated_client.user)
        quota.storage_limit_bytes = 1000
        quota.storage_used_bytes = 900
        quota.save()
        
        # Upload file that exactly reaches limit
        content = b'X' * 100
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        # Should succeed
        assert response.status_code == status.HTTP_201_CREATED
        
        quota.refresh_from_db()
        assert quota.storage_used_bytes == 1000
    
    def test_multiple_uploads_quota_accumulation(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that multiple uploads accumulate against quota"""
        quota = UserQuota.objects.get(user=authenticated_client.user)
        initial_usage = quota.storage_used_bytes
        
        # Upload multiple files
        for i in range(5):
            content = b'X' * 1000
            file = SimpleUploadedFile(f'test{i}.txt', content, content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            assert response.status_code == status.HTTP_201_CREATED
        
        quota.refresh_from_db()
        assert quota.storage_used_bytes == initial_usage + (5 * 1000)
    
    def test_delete_frees_quota(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that deleting files frees up quota for new uploads"""
        quota = UserQuota.objects.get(user=authenticated_client.user)
        quota.storage_limit_bytes = 2000
        quota.storage_used_bytes = 0
        quota.save()
        
        # Upload file using quota
        content1 = b'X' * 1500
        file1 = SimpleUploadedFile('test1.txt', content1, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        file1_id = response1.data['file_id']
        
        # Try to upload another - should fail
        content2 = b'Y' * 1000
        file2 = SimpleUploadedFile('test2.txt', content2, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        
        # Delete first file
        authenticated_client.delete(f'/api/files/{file1_id}/delete/')
        
        # Now upload should succeed
        file3 = SimpleUploadedFile('test3.txt', content2, content_type='text/plain')
        response3 = authenticated_client.post('/api/files/upload/', {
            'file': file3
        }, format='multipart')
        assert response3.status_code == status.HTTP_201_CREATED
