"""
Tests for deduplication functionality.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from data.models import StoredFile, ObjectChunk


@pytest.mark.django_db
class TestDeduplication:
    """Test chunk deduplication"""
    
    def test_identical_files_share_chunks(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that uploading identical files shares chunks"""
        content = b'Identical content for dedup test'
        
        # Upload first file
        file1 = SimpleUploadedFile('file1.txt', content, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Upload identical file
        file2 = SimpleUploadedFile('file2.txt', content, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        assert response2.status_code == status.HTTP_201_CREATED
        
        # Get stored files
        stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
        stored_file2 = StoredFile.objects.get(id=response2.data['file_id'])
        
        # Verify same chunks used
        chunks1 = list(stored_file1.chunks.all())
        chunks2 = list(stored_file2.chunks.all())
        
        assert len(chunks1) == len(chunks2)
        for chunk1, chunk2 in zip(chunks1, chunks2):
            assert chunk1.chunk.checksum == chunk2.chunk.checksum
    
    def test_ref_count_increases(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that ref_count increases when chunks are reused"""
        content = b'Content for ref count test'
        
        # Upload first file
        file1 = SimpleUploadedFile('file1.txt', content, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        
        # Get chunk ref_count
        stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
        chunk1 = stored_file1.chunks.first()
        initial_ref_count = chunk1.chunk.ref_count
        
        # Upload identical file
        file2 = SimpleUploadedFile('file2.txt', content, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        
        # Verify ref_count increased
        chunk1.refresh_from_db()
        assert chunk1.chunk.ref_count == initial_ref_count + 1
    
    def test_partial_dedup(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test deduplication with partially overlapping content"""
        chunk_size = 256 * 1024
        shared_chunk = b'A' * chunk_size
        unique_chunk1 = b'B' * chunk_size
        unique_chunk2 = b'C' * chunk_size
        
        # Upload file with shared + unique content
        content1 = shared_chunk + unique_chunk1
        file1 = SimpleUploadedFile('file1.bin', content1, content_type='application/octet-stream')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        
        # Upload file with same shared chunk but different unique chunk
        content2 = shared_chunk + unique_chunk2
        file2 = SimpleUploadedFile('file2.bin', content2, content_type='application/octet-stream')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        
        # Get chunks
        stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
        stored_file2 = StoredFile.objects.get(id=response2.data['file_id'])
        
        chunks1 = list(stored_file1.chunks.all().order_by('sequence_no'))
        chunks2 = list(stored_file2.chunks.all().order_by('sequence_no'))
        
        # First chunks should be identical (shared)
        assert chunks1[0].chunk.checksum == chunks2[0].chunk.checksum
        assert chunks1[0].chunk.ref_count == 2
        
        # Second chunks should be different (unique)
        assert chunks1[1].chunk.checksum != chunks2[1].chunk.checksum
        assert chunks1[1].chunk.ref_count == 1
        assert chunks2[1].chunk.ref_count == 1
    
    def test_dedup_across_users(self, api_client, user_factory, mock_object_storage, disable_rate_limiting):
        """Test that deduplication works across different users"""
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # Create two users
        user1 = user_factory(username='user1')
        user2 = user_factory(username='user2')
        
        content = b'Shared content across users'
        
        # Upload as user1
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user1).access_token)}')
        file1 = SimpleUploadedFile('user1_file.txt', content, content_type='text/plain')
        response1 = api_client.post('/api/files/upload/', {'file': file1}, format='multipart')
        
        # Upload as user2
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user2).access_token)}')
        file2 = SimpleUploadedFile('user2_file.txt', content, content_type='text/plain')
        response2 = api_client.post('/api/files/upload/', {'file': file2}, format='multipart')
        
        # Verify chunks are shared
        stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
        stored_file2 = StoredFile.objects.get(id=response2.data['file_id'])
        
        chunk1 = stored_file1.chunks.first()
        chunk2 = stored_file2.chunks.first()
        
        assert chunk1.chunk.checksum == chunk2.chunk.checksum
        assert chunk1.chunk.ref_count == 2
    
    def test_no_duplicate_chunk_storage(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that duplicate chunks aren't stored multiple times"""
        content = b'No duplicate storage test'
        
        # Upload first file
        file1 = SimpleUploadedFile('file1.txt', content, content_type='text/plain')
        authenticated_client.post('/api/files/upload/', {'file': file1}, format='multipart')
        
        initial_chunk_count = ObjectChunk.objects.count()
        
        # Upload identical file
        file2 = SimpleUploadedFile('file2.txt', content, content_type='text/plain')
        authenticated_client.post('/api/files/upload/', {'file': file2}, format='multipart')
        
        # Verify no new chunks created
        final_chunk_count = ObjectChunk.objects.count()
        assert final_chunk_count == initial_chunk_count
    
    def test_checksum_collision_handling(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that SHA256 checksums uniquely identify chunks"""
        # Two different contents should produce different checksums
        content1 = b'Content one for checksum test'
        content2 = b'Content two for checksum test'
        
        file1 = SimpleUploadedFile('file1.txt', content1, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {'file': file1}, format='multipart')
        
        file2 = SimpleUploadedFile('file2.txt', content2, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {'file': file2}, format='multipart')
        
        stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
        stored_file2 = StoredFile.objects.get(id=response2.data['file_id'])
        
        chunk1 = stored_file1.chunks.first()
        chunk2 = stored_file2.chunks.first()
        
        # Different content = different checksums
        assert chunk1.chunk.checksum != chunk2.chunk.checksum

