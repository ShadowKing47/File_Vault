"""
Tests for file download functionality.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from data.models import StoredFile
import hashlib


@pytest.mark.django_db
class TestFileDownload:
    """Test file download endpoint"""
    
    def test_download_small_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test downloading a small file"""
        content = b'Hello, World!'
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        
        # Upload file
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Download file
        download_response = authenticated_client.get(f'/api/files/{file_id}/download/')
        
        assert download_response.status_code == status.HTTP_200_OK
        assert b''.join(download_response.streaming_content) == content
    
    def test_download_medium_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test downloading a medium-sized file (1MB)"""
        content = b'X' * (1024 * 1024)
        file = SimpleUploadedFile('medium.bin', content, content_type='application/octet-stream')
        
        # Upload file
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Download file
        download_response = authenticated_client.get(f'/api/files/{file_id}/download/')
        
        assert download_response.status_code == status.HTTP_200_OK
        downloaded_content = b''.join(download_response.streaming_content)
        assert downloaded_content == content
    
    def test_download_nonexistent_file(self, authenticated_client, disable_rate_limiting):
        """Test downloading file that doesn't exist"""
        response = authenticated_client.get('/api/files/99999/download/')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_download_other_users_file(self, api_client, user_factory, mock_object_storage, disable_rate_limiting):
        """Test that users cannot download other users' files"""
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # User1 uploads file
        user1 = user_factory(username='user1')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user1).access_token)}')
        
        content = b'Private content'
        file = SimpleUploadedFile('private.txt', content, content_type='text/plain')
        upload_response = api_client.post('/api/files/upload/', {'file': file}, format='multipart')
        file_id = upload_response.data['file_id']
        
        # User2 tries to download
        user2 = user_factory(username='user2')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user2).access_token)}')
        
        download_response = api_client.get(f'/api/files/{file_id}/download/')
        
        assert download_response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
    
    def test_download_content_integrity(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that downloaded content matches uploaded content"""
        # Upload various content types
        test_cases = [
            (b'Simple text', 'text.txt'),
            (b'\x00\x01\x02\x03\x04\x05', 'binary.bin'),
            (b'A' * 10000, 'large_text.txt'),
            (bytes(range(256)), 'all_bytes.bin')
        ]
        
        for content, filename in test_cases:
            # Upload
            file = SimpleUploadedFile(filename, content, content_type='application/octet-stream')
            upload_response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            file_id = upload_response.data['file_id']
            
            # Download
            download_response = authenticated_client.get(f'/api/files/{file_id}/download/')
            downloaded_content = b''.join(download_response.streaming_content)
            
            # Verify integrity
            assert downloaded_content == content
            assert hashlib.sha256(downloaded_content).hexdigest() == hashlib.sha256(content).hexdigest()
    
    def test_download_streaming_response(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that download uses streaming response"""
        content = b'X' * (512 * 1024)  # 512KB
        file = SimpleUploadedFile('stream.bin', content, content_type='application/octet-stream')
        
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        download_response = authenticated_client.get(f'/api/files/{file_id}/download/')
        
        # Check it's a streaming response
        assert hasattr(download_response, 'streaming_content')
    
    def test_download_empty_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test downloading empty file"""
        file = SimpleUploadedFile('empty.txt', b'', content_type='text/plain')
        
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        download_response = authenticated_client.get(f'/api/files/{file_id}/download/')
        
        assert download_response.status_code == status.HTTP_200_OK
        assert b''.join(download_response.streaming_content) == b''
    
    def test_download_unauthenticated(self, api_client, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test download without authentication"""
        # Upload file as authenticated user
        content = b'test content'
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        # Try to download without auth
        download_response = api_client.get(f'/api/files/{file_id}/download/')
        
        assert download_response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestChunkReconstruction:
    """Test file reconstruction from chunks"""
    
    def test_multi_chunk_file_reconstruction(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that multi-chunk files are correctly reconstructed"""
        chunk_size = 256 * 1024
        chunk1_content = b'A' * chunk_size
        chunk2_content = b'B' * chunk_size
        chunk3_content = b'C' * 1000
        content = chunk1_content + chunk2_content + chunk3_content
        
        file = SimpleUploadedFile('multi.bin', content, content_type='application/octet-stream')
        
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        download_response = authenticated_client.get(f'/api/files/{file_id}/download/')
        downloaded_content = b''.join(download_response.streaming_content)
        
        assert downloaded_content == content
        assert len(downloaded_content) == len(content)
    
    def test_chunk_order_preserved(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that chunk order is preserved during reconstruction"""
        chunk_size = 256 * 1024
        content = b''.join([bytes([i % 256]) * chunk_size for i in range(3)])
        
        file = SimpleUploadedFile('ordered.bin', content, content_type='application/octet-stream')
        
        upload_response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        file_id = upload_response.data['file_id']
        
        download_response = authenticated_client.get(f'/api/files/{file_id}/download/')
        downloaded_content = b''.join(download_response.streaming_content)
        
        # Verify exact match
        assert downloaded_content == content
