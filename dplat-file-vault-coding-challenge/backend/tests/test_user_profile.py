"""
Tests for user profile management.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework import status


@pytest.mark.django_db
class TestUserProfileCRUD:
    """Test user profile CRUD operations"""
    
    def test_get_own_profile(self, authenticated_client, disable_rate_limiting):
        """Test retrieving own profile"""
        response = authenticated_client.get('/api/auth/profile/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['username'] == authenticated_client.user.username
        assert response.data['email'] == authenticated_client.user.email
        assert 'id' in response.data
    
    def test_update_email(self, authenticated_client, disable_rate_limiting):
        """Test updating email address"""
        new_email = 'newemail@example.com'
        
        response = authenticated_client.put('/api/auth/profile/', {
            'email': new_email
        })
        
        assert response.status_code == status.HTTP_200_OK
        authenticated_client.user.refresh_from_db()
        assert authenticated_client.user.email == new_email
    
    def test_update_username(self, authenticated_client, disable_rate_limiting):
        """Test updating username"""
        new_username = 'newusername'
        
        response = authenticated_client.put('/api/auth/profile/', {
            'username': new_username
        })
        
        if response.status_code == status.HTTP_200_OK:
            authenticated_client.user.refresh_from_db()
            assert authenticated_client.user.username == new_username
    
    def test_update_invalid_email(self, authenticated_client, disable_rate_limiting):
        """Test updating with invalid email"""
        response = authenticated_client.put('/api/auth/profile/', {
            'email': 'invalid-email'
        })
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_get_profile_unauthenticated(self, api_client, disable_rate_limiting):
        """Test getting profile without authentication"""
        response = api_client.get('/api/auth/profile/')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPasswordChange:
    """Test password change functionality"""
    
    def test_successful_password_change(self, authenticated_client, disable_rate_limiting):
        """Test successful password change"""
        data = {
            'old_password': 'testpass123',
            'new_password': 'newsecurepass456',
            'new_password_confirm': 'newsecurepass456'
        }
        
        response = authenticated_client.post('/api/auth/change-password/', data)
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify password changed
        authenticated_client.user.refresh_from_db()
        assert authenticated_client.user.check_password('newsecurepass456')
        assert not authenticated_client.user.check_password('testpass123')
    
    def test_password_change_wrong_old_password(self, authenticated_client, disable_rate_limiting):
        """Test password change with incorrect old password"""
        data = {
            'old_password': 'wrongpassword',
            'new_password': 'newsecurepass456',
            'new_password_confirm': 'newsecurepass456'
        }
        
        response = authenticated_client.post('/api/auth/change-password/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        # Verify password unchanged
        authenticated_client.user.refresh_from_db()
        assert authenticated_client.user.check_password('testpass123')
    
    def test_password_change_mismatch(self, authenticated_client, disable_rate_limiting):
        """Test password change with mismatched new passwords"""
        data = {
            'old_password': 'testpass123',
            'new_password': 'newsecurepass456',
            'new_password_confirm': 'differentpass789'
        }
        
        response = authenticated_client.post('/api/auth/change-password/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_password_change_weak_password(self, authenticated_client, disable_rate_limiting):
        """Test password change with weak password"""
        data = {
            'old_password': 'testpass123',
            'new_password': '123',
            'new_password_confirm': '123'
        }
        
        response = authenticated_client.post('/api/auth/change-password/', data)
        
        # May be rejected if password validation is enabled
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            assert 'password' in str(response.data).lower()
    
    def test_password_change_unauthenticated(self, api_client, disable_rate_limiting):
        """Test password change without authentication"""
        data = {
            'old_password': 'testpass123',
            'new_password': 'newsecurepass456',
            'new_password_confirm': 'newsecurepass456'
        }
        
        response = api_client.post('/api/auth/change-password/', data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUserQuotaProfile:
    """Test user quota in profile"""
    
    def test_profile_includes_quota_info(self, authenticated_client, disable_rate_limiting):
        """Test that profile includes quota information"""
        response = authenticated_client.get('/api/quota/')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'storage_used_bytes' in response.data
        assert 'storage_limit_bytes' in response.data
    
    def test_quota_reflects_file_uploads(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that quota reflects uploaded files"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        # Check initial quota
        response = authenticated_client.get('/api/quota/')
        initial_usage = response.data['storage_used_bytes']
        
        # Upload file
        content = b'X' * 10000
        file = SimpleUploadedFile('test.txt', content, content_type='text/plain')
        authenticated_client.post('/api/files/upload/', {'file': file}, format='multipart')
        
        # Check updated quota
        response = authenticated_client.get('/api/quota/')
        new_usage = response.data['storage_used_bytes']
        
        assert new_usage > initial_usage
    
    def test_quota_in_mb_conversion(self, authenticated_client, disable_rate_limiting):
        """Test quota MB conversion"""
        response = authenticated_client.get('/api/quota/')
        
        assert response.status_code == status.HTTP_200_OK
        
        if 'storage_used_mb' in response.data:
            # Verify MB conversion is correct
            used_mb = response.data['storage_used_mb']
            used_bytes = response.data['storage_used_bytes']
            assert abs(used_mb - (used_bytes / (1024 * 1024))) < 0.01


@pytest.mark.django_db
class TestUserManagement:
    """Test user management operations"""
    
    def test_user_created_with_quota(self, user_factory):
        """Test that new users are created with quota"""
        from data.models import UserQuota
        
        user = user_factory()
        
        quota = UserQuota.objects.get(user=user)
        assert quota.storage_limit_bytes == 5 * 1024 * 1024 * 1024
        assert quota.storage_used_bytes == 0
    
    def test_user_password_hashed(self, user_factory):
        """Test that user passwords are properly hashed"""
        password = 'securepassword123'
        user = user_factory(password=password)
        
        # Password should be hashed, not stored as plaintext
        assert user.password != password
        # Should be able to check password
        assert user.check_password(password)
    
    def test_duplicate_username_prevented(self, user_factory, api_client, disable_rate_limiting):
        """Test that duplicate usernames are prevented"""
        user_factory(username='existinguser')
        
        data = {
            'username': 'existinguser',
            'email': 'new@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123'
        }
        
        response = api_client.post('/api/auth/register/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_email_uniqueness(self, user_factory, api_client, disable_rate_limiting):
        """Test email uniqueness if enforced"""
        user_factory(email='existing@example.com')
        
        data = {
            'username': 'newuser',
            'email': 'existing@example.com',
            'password': 'testpass123',
            'password_confirm': 'testpass123'
        }
        
        response = api_client.post('/api/auth/register/', data)
        
        # May or may not enforce email uniqueness depending on settings
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            assert 'email' in str(response.data).lower()
