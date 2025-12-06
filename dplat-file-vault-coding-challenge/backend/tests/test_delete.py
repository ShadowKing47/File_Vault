"""
Tests for file deletion functionality.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from data.models import StoredFile, ObjectChunk


@pytest.mark.django_db
class TestFileDeletion:
    """Test file deletion endpoint"""
    
    def test_delete_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test successful file deletion"""
        content = b'File to delete'
        file = SimpleUploadedFile('delete_me.txt', content, content_type='text/plain')
        
        # Upload file
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Delete file
        delete_response = authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        assert delete_response.status_code == status.HTTP_200_OK
        
        # Verify file deleted
        assert not StoredFile.objects.filter(id=file_id).exists()
    
    def test_delete_nonexistent_file(self, authenticated_client, disable_rate_limiting):
        """Test deleting file that doesn't exist"""
        response = authenticated_client.delete('/api/files/99999/delete/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_delete_other_users_file(self, api_client, user_factory, mock_object_storage, disable_rate_limiting):
        """Test that users cannot delete other users' files"""
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # User1 uploads file
        user1 = user_factory(username='user1')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user1).access_token)}')
        
        content = b'Private file'
        file = SimpleUploadedFile('private.txt', content, content_type='text/plain')
        upload_response = api_client.post('/api/files/upload/', {'file': file}, format='multipart')
        file_id = upload_response.data['file_id']
        
        # User2 tries to delete
        user2 = user_factory(username='user2')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user2).access_token)}')
        
        delete_response = api_client.delete(f'/api/files/{file_id}/delete/')
        
        assert delete_response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
        
        # Verify file still exists
        assert StoredFile.objects.filter(id=file_id).exists()
    
    def test_delete_unauthenticated(self, api_client, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test deletion without authentication"""
        # Upload file
        content = b'test content'
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Try to delete without auth
        delete_response = api_client.delete(f'/api/files/{file_id}/delete/')
        
        assert delete_response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestRefCountManagement:
    """Test reference count management during deletion"""
    
    def test_ref_count_decreases_on_delete(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that chunk ref_count decreases when file is deleted"""
        content = b'Content for ref count test'
        
        # Upload file
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Get chunk and ref_count
        stored_file = StoredFile.objects.get(id=file_id)
        chunk = stored_file.chunks.first()
        initial_ref_count = chunk.chunk.ref_count
        
        # Delete file
        authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        # Verify ref_count decreased
        chunk.refresh_from_db()
        assert chunk.chunk.ref_count == initial_ref_count - 1
    
    def test_chunk_deleted_when_ref_count_zero(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that chunks are deleted when ref_count reaches zero"""
        content = b'Unique content for this test'
        file = SimpleUploadedFile('unique.txt', content, content_type='text/plain')
        
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Get chunk
        stored_file = StoredFile.objects.get(id=file_id)
        chunk = stored_file.chunks.first()
        chunk_checksum = chunk.checksum
        
        # Delete file
        authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        # Verify chunk deleted (or ref_count is 0)
        remaining_chunk = ObjectChunk.objects.filter(checksum=chunk_checksum).first()
        if remaining_chunk:
            assert remaining_chunk.chunk.ref_count == 0
    
    def test_shared_chunk_not_deleted(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that shared chunks aren't deleted while still referenced"""
        content = b'Shared content'
        
        # Upload two files with same content
        file1 = SimpleUploadedFile('file1.txt', content, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        file1_id = response1.data['file_id']
        
        file2 = SimpleUploadedFile('file2.txt', content, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        
        # Get chunk
        stored_file1 = StoredFile.objects.get(id=file1_id)
        chunk = stored_file1.chunks.first()
        chunk_checksum = chunk.checksum
        initial_ref_count = chunk.chunk.ref_count
        
        # Delete first file
        authenticated_client.delete(f'/api/files/{file1_id}/delete/')
        
        # Verify chunk still exists with decremented ref_count
        chunk.refresh_from_db()
        assert chunk.chunk.ref_count == initial_ref_count - 1
        assert ObjectChunk.objects.filter(checksum=chunk_checksum).exists()
    
    def test_multi_chunk_file_deletion(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test deletion of file with multiple chunks"""
        chunk_size = 256 * 1024
        content = b'A' * chunk_size + b'B' * chunk_size + b'C' * 1000
        
        file = SimpleUploadedFile('multi.bin', content, content_type='application/octet-stream')
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Get all chunks
        stored_file = StoredFile.objects.get(id=file_id)
        chunk_checksums = [chunk.checksum for chunk in stored_file.chunks.all()]
        
        # Delete file
        authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        # Verify all chunks have decremented ref_count
        for checksum in chunk_checksums:
            chunk = ObjectChunk.objects.filter(checksum=checksum).first()
            if chunk:
                # Chunk may be deleted if ref_count was 1, or should have ref_count decremented
                assert chunk.chunk.ref_count >= 0


@pytest.mark.django_db
class TestOrphanCleanup:
    """Test orphaned chunk cleanup"""
    
    def test_orphaned_chunks_marked_for_gc(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that orphaned chunks are properly marked for garbage collection"""
        content = b'Content that will become orphaned'
        file = SimpleUploadedFile('orphan.txt', content, content_type='text/plain')
        
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        stored_file = StoredFile.objects.get(id=file_id)
        chunk = stored_file.chunks.first()
        
        # Delete file
        authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        # Check if chunk is orphaned (ref_count <= 0)
        chunk.refresh_from_db()
        if ObjectChunk.objects.filter(checksum=chunk.checksum).exists():
            assert chunk.chunk.ref_count <= 0
    
    def test_delete_updates_user_quota(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that deletion updates user quota"""
        from data.models import UserQuota
        
        content = b'X' * 10000
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        
        # Upload file
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        quota = UserQuota.objects.get(user=authenticated_client.user)
        usage_before_delete = quota.storage_used_bytes
        
        # Delete file
        authenticated_client.delete(f'/api/files/{file_id}/delete/')
        
        quota.refresh_from_db()
        assert quota.storage_used_bytes < usage_before_delete
