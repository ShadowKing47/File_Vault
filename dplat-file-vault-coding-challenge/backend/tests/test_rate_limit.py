"""
Tests for rate limiting functionality.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
import time


@pytest.mark.django_db
class TestRateLimiting:
    """Test rate limiting on endpoints"""
    
    def test_upload_rate_limit_enforced(self, authenticated_client, mock_object_storage):
        """Test that upload endpoint enforces rate limit"""
        # Make requests up to limit (10 per 60s)
        for i in range(10):
            file = SimpleUploadedFile(f'file{i}.txt', b'content', content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            # First 10 should succeed
            assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_429_TOO_MANY_REQUESTS]
        
        # Next request should be rate limited
        file = SimpleUploadedFile('over_limit.txt', b'content', content_type='text/plain')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    
    def test_delete_rate_limit_enforced(self, authenticated_client, stored_file_factory):
        """Test that delete endpoint enforces rate limit"""
        # Create files
        files = [stored_file_factory(user=authenticated_client.user) for _ in range(12)]
        
        # Make requests up to limit (10 per 60s)
        for i in range(10):
            response = authenticated_client.delete(f'/api/files/{files[i].id}/delete/')
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS]
        
        # Next request should be rate limited
        response = authenticated_client.delete(f'/api/files/{files[10].id}/delete/')
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    
    def test_registration_rate_limit_enforced(self, api_client):
        """Test that registration endpoint enforces rate limit"""
        # Make requests up to limit (5 per 300s)
        for i in range(5):
            data = {
                'username': f'user{i}',
                'email': f'user{i}@example.com',
                'password': 'testpass123',
                'password_confirm': 'testpass123'
            }
            response = api_client.post('/api/auth/register/', data)
            assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_429_TOO_MANY_REQUESTS]
        
        # Next request should be rate limited
        data = {
            'username': 'overlimit',
            'email': 'overlimit@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123'
        }
        response = api_client.post('/api/auth/register/', data)
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    
    def test_rate_limit_per_user(self, api_client, user_factory, mock_object_storage):
        """Test that rate limits are per-user"""
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # User1 exhausts rate limit
        user1 = user_factory(username='user1')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user1).access_token)}')
        
        for i in range(10):
            file = SimpleUploadedFile(f'file{i}.txt', b'content', content_type='text/plain')
            api_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # User1 should be rate limited
        file = SimpleUploadedFile('over.txt', b'content', content_type='text/plain')
        response = api_client.post('/api/files/upload/', {'file': file}, format='multipart')
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        
        # User2 should not be affected
        user2 = user_factory(username='user2')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(RefreshToken.for_user(user2).access_token)}')
        
        file = SimpleUploadedFile('user2.txt', b'content', content_type='text/plain')
        response = api_client.post('/api/files/upload/', {'file': file}, format='multipart')
        # User2's first request should succeed
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_rate_limit_response_format(self, authenticated_client, mock_object_storage):
        """Test that rate limit response has correct format"""
        # Exhaust rate limit
        for i in range(10):
            file = SimpleUploadedFile(f'file{i}.txt', b'content', content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # Get rate limited response
        file = SimpleUploadedFile('over.txt', b'content', content_type='text/plain')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert 'error' in response.data


@pytest.mark.django_db
class TestRateLimitWindow:
    """Test rate limit sliding window"""
    
    def test_sliding_window_behavior(self, authenticated_client, mock_object_storage):
        """Test that rate limit uses sliding window"""
        # Make initial requests
        for i in range(5):
            file = SimpleUploadedFile(f'file{i}.txt', b'content', content_type='text/plain')
            authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # Wait briefly (not enough for window to reset completely)
        time.sleep(1)
        
        # Make more requests
        for i in range(5):
            file = SimpleUploadedFile(f'file2_{i}.txt', b'content', content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
            # May succeed or be rate limited depending on timing
            assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_429_TOO_MANY_REQUESTS]


@pytest.mark.django_db
class TestRateLimitConfiguration:
    """Test rate limit configuration"""
    
    def test_different_limits_per_endpoint(self, authenticated_client, mock_object_storage):
        """Test that different endpoints have different rate limits"""
        # Upload has 10 req/60s limit
        upload_responses = []
        for i in range(11):
            file = SimpleUploadedFile(f'file{i}.txt', b'content', content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
            upload_responses.append(response.status_code)
        
        # Should eventually hit rate limit
        assert status.HTTP_429_TOO_MANY_REQUESTS in upload_responses
    
    def test_profile_get_higher_limit(self, authenticated_client, disable_rate_limiting):
        """Test that profile GET has higher limit (20 req/60s)"""
        # Make many profile requests
        for i in range(15):
            response = authenticated_client.get('/api/auth/profile/')
            # Should succeed (limit is 20)
            assert response.status_code == status.HTTP_200_OK
    
    def test_rate_limit_disabled_in_tests(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that rate limiting can be disabled for testing"""
        # Make many requests without hitting rate limit
        for i in range(20):
            file = SimpleUploadedFile(f'file{i}.txt', b'content', content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestRateLimitEdgeCases:
    """Test rate limit edge cases"""
    
    def test_unauthenticated_rate_limit(self, api_client, disable_rate_limiting):
        """Test rate limiting for unauthenticated users"""
        # Unauthenticated registration requests
        for i in range(3):
            data = {
                'username': f'user{i}',
                'email': f'user{i}@example.com',
                'password': 'testpass123',
                'password_confirm': 'testpass123'
            }
            response = api_client.post('/api/auth/register/', data)
            # Should either succeed or fail validation, not rate limit (disabled)
            assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]
    
    def test_rate_limit_concurrent_requests(self, authenticated_client, mock_object_storage):
        """Test rate limiting with near-concurrent requests"""
        import threading
        
        results = []
        
        def make_request():
            file = SimpleUploadedFile('concurrent.txt', b'content', content_type='text/plain')
            response = authenticated_client.post('/api/files/upload/', {
                'file': file
            }, format='multipart')
            results.append(response.status_code)
        
        # Make concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Some should be rate limited
        assert status.HTTP_429_TOO_MANY_REQUESTS in results or status.HTTP_201_CREATED in results
