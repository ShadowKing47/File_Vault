"""
Tests for authentication and user management.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework import status


@pytest.mark.django_db
class TestUserRegistration:
    """Test user registration endpoint"""
    
    def test_successful_registration(self, api_client, disable_rate_limiting):
        """Test successful user registration"""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
            'password_confirm': 'securepass123'
        }
        response = api_client.post('/api/auth/register/', data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'username' in response.data
        assert response.data['username'] == 'newuser'
        
        # Verify user created
        user = User.objects.get(username='newuser')
        assert user.email == 'newuser@example.com'
        assert user.check_password('securepass123')
    
    def test_registration_password_mismatch(self, api_client, disable_rate_limiting):
        """Test registration with mismatched passwords"""
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
            'password_confirm': 'differentpass'
        }
        response = api_client.post('/api/auth/register/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_registration_duplicate_username(self, api_client, user_factory, disable_rate_limiting):
        """Test registration with existing username"""
        user_factory(username='existinguser')
        
        data = {
            'username': 'existinguser',
            'email': 'new@example.com',
            'password': 'securepass123',
            'password_confirm': 'securepass123'
        }
        response = api_client.post('/api/auth/register/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_registration_invalid_email(self, api_client, disable_rate_limiting):
        """Test registration with invalid email"""
        data = {
            'username': 'newuser',
            'email': 'invalid-email',
            'password': 'securepass123',
            'password_confirm': 'securepass123'
        }
        response = api_client.post('/api/auth/register/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestJWTAuthentication:
    """Test JWT token authentication"""
    
    def test_obtain_token_success(self, api_client, user_factory, disable_rate_limiting):
        """Test obtaining JWT token with valid credentials"""
        user_factory(username='testuser', password='testpass123')
        
        response = api_client.post('/api/auth/token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
    
    def test_obtain_token_invalid_credentials(self, api_client, user_factory, disable_rate_limiting):
        """Test obtaining token with invalid credentials"""
        user_factory(username='testuser', password='testpass123')
        
        response = api_client.post('/api/auth/token/', {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_refresh_token(self, api_client, user_factory, disable_rate_limiting):
        """Test refreshing JWT token"""
        user_factory(username='testuser', password='testpass123')
        
        # Obtain token
        response = api_client.post('/api/auth/token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        refresh_token = response.data['refresh']
        
        # Refresh token
        response = api_client.post('/api/auth/token/refresh/', {
            'refresh': refresh_token
        })
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
    
    def test_authenticated_request(self, authenticated_client, disable_rate_limiting):
        """Test making authenticated request"""
        response = authenticated_client.get('/api/auth/profile/')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'username' in response.data
    
    def test_unauthenticated_request(self, api_client, disable_rate_limiting):
        """Test making request without authentication"""
        response = api_client.get('/api/auth/profile/')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUserProfile:
    """Test user profile endpoints"""
    
    def test_get_profile(self, authenticated_client, disable_rate_limiting):
        """Test retrieving user profile"""
        response = authenticated_client.get('/api/auth/profile/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['username'] == authenticated_client.user.username
        assert response.data['email'] == authenticated_client.user.email
    
    def test_update_profile(self, authenticated_client, disable_rate_limiting):
        """Test updating user profile"""
        data = {
            'email': 'newemail@example.com'
        }
        response = authenticated_client.put('/api/auth/profile/', data)
        
        assert response.status_code == status.HTTP_200_OK
        authenticated_client.user.refresh_from_db()
        assert authenticated_client.user.email == 'newemail@example.com'
    
    def test_change_password_success(self, authenticated_client, disable_rate_limiting):
        """Test successful password change"""
        data = {
            'old_password': 'testpass123',
            'new_password': 'newsecurepass123',
            'new_password_confirm': 'newsecurepass123'
        }
        response = authenticated_client.post('/api/auth/change-password/', data)
        
        assert response.status_code == status.HTTP_200_OK
        authenticated_client.user.refresh_from_db()
        assert authenticated_client.user.check_password('newsecurepass123')
    
    def test_change_password_wrong_old_password(self, authenticated_client, disable_rate_limiting):
        """Test password change with wrong old password"""
        data = {
            'old_password': 'wrongpassword',
            'new_password': 'newsecurepass123',
            'new_password_confirm': 'newsecurepass123'
        }
        response = authenticated_client.post('/api/auth/change-password/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_change_password_mismatch(self, authenticated_client, disable_rate_limiting):
        """Test password change with mismatched new passwords"""
        data = {
            'old_password': 'testpass123',
            'new_password': 'newsecurepass123',
            'new_password_confirm': 'differentpass'
        }
        response = authenticated_client.post('/api/auth/change-password/', data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
