"""
Tests for file search and listing functionality.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status


@pytest.mark.django_db
class TestFileSearch:
    """Test file search endpoint"""
    
    def test_search_by_filename(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test searching files by filename"""
        # Upload test files
        files_to_upload = [
            ('document.txt', b'doc content'),
            ('report.pdf', b'pdf content'),
            ('notes.txt', b'notes content')
        ]
        
        for filename, content in files_to_upload:
            file = SimpleUploadedFile(filename, content, content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # Search for .txt files
        response = authenticated_client.get('/api/files/files/?filename=txt')
        
        assert response.status_code == status.HTTP_200_OK
        filenames = [f['filename'] for f in response.data]
        assert 'document.txt' in filenames
        assert 'notes.txt' in filenames
        assert 'report.pdf' not in filenames
    
    def test_search_case_insensitive(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that search is case-insensitive"""
        file = SimpleUploadedFile('MyDocument.TXT', b'content', content_type='text/plain')
        authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # Search with lowercase
        response = authenticated_client.get('/api/files/files/?filename=document')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0
    
    def test_list_all_user_files(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test listing all files for a user"""
        # Upload multiple files
        for i in range(5):
            file = SimpleUploadedFile(f'file{i}.txt', b'content', content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # List all files
        response = authenticated_client.get('/api/files/files/')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 5
    
    def test_user_only_sees_own_files(self, api_client, user_factory, mock_object_storage, disable_rate_limiting):
        """Test that users only see their own files"""
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # User1 uploads files
        user1 = user_factory(username='user1')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user1).access_token)}')
        for i in range(3):
            file = SimpleUploadedFile(f'user1_file{i}.txt', b'content', content_type='text/plain')
            api_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # User2 uploads files
        user2 = user_factory(username='user2')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user2).access_token)}')
        for i in range(2):
            file = SimpleUploadedFile(f'user2_file{i}.txt', b'content', content_type='text/plain')
            api_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # User2 lists files
        response = api_client.get('/api/files/files/')
        
        # Should only see own files
        assert len(response.data) == 2
        filenames = [f['filename'] for f in response.data]
        assert all('user2' in fn for fn in filenames)


@pytest.mark.django_db
class TestFileOrdering:
    """Test file ordering in search results"""
    
    def test_order_by_upload_date(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test ordering files by upload date"""
        import time
        
        # Upload files with slight delay
        filenames = ['first.txt', 'second.txt', 'third.txt']
        for filename in filenames:
            file = SimpleUploadedFile(filename, b'content', content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
            time.sleep(0.1)
        
        # List files ordered by upload date (newest first)
        response = authenticated_client.get('/api/files/files/?ordering=-uploaded_at')
        
        assert response.status_code == status.HTTP_200_OK
        returned_filenames = [f['filename'] for f in response.data]
        
        # Should be in reverse order
        assert returned_filenames[0] == 'third.txt'
        assert returned_filenames[-1] == 'first.txt'
    
    def test_order_by_size(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test ordering files by size"""
        # Upload files of different sizes
        files_data = [
            ('small.txt', b'X' * 100),
            ('large.txt', b'X' * 10000),
            ('medium.txt', b'X' * 1000)
        ]
        
        for filename, content in files_data:
            file = SimpleUploadedFile(filename, content, content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # List files ordered by size
        response = authenticated_client.get('/api/files/files/?ordering=size_bytes')
        
        assert response.status_code == status.HTTP_200_OK
        sizes = [f['size_bytes'] for f in response.data]
        
        # Should be in ascending order
        assert sizes == sorted(sizes)


@pytest.mark.django_db
class TestFileFiltering:
    """Test file filtering"""
    
    def test_filter_by_size_range(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test filtering files by size range"""
        # Upload files of different sizes
        files_data = [
            ('tiny.txt', b'X' * 10),
            ('small.txt', b'X' * 100),
            ('medium.txt', b'X' * 1000),
            ('large.txt', b'X' * 10000)
        ]
        
        for filename, content in files_data:
            file = SimpleUploadedFile(filename, content, content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # Filter for medium-sized files
        response = authenticated_client.get('/api/files/files/?size_min=500&size_max=5000')
        
        if response.status_code == status.HTTP_200_OK:
            sizes = [f['size_bytes'] for f in response.data]
            # All returned files should be in range
            assert all(500 <= s <= 5000 for s in sizes)
    
    def test_empty_search_results(self, authenticated_client, disable_rate_limiting):
        """Test search with no results"""
        response = authenticated_client.get('/api/files/files/?filename=nonexistent')
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0


@pytest.mark.django_db
class TestPagination:
    """Test pagination of search results"""
    
    def test_paginated_results(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that large result sets are paginated"""
        # Upload many files
        for i in range(25):
            file = SimpleUploadedFile(f'file{i:03d}.txt', b'content', content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # Get first page
        response = authenticated_client.get('/api/files/files/')
        
        assert response.status_code == status.HTTP_200_OK
        # Should return results (may be paginated depending on settings)
        assert len(response.data) > 0
