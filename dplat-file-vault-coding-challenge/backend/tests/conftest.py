"""
Pytest configuration and shared fixtures.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from data.models import UserQuota, ObjectChunk, StoredFile
from tests.mocks.mock_object_store import mock_store
import io


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """Enable database access for all tests"""
    pass


@pytest.fixture(autouse=True)
def reset_mock_storage():
    """Reset mock storage before each test"""
    mock_store.reset()
    mock_store.set_nodes(['node1', 'node2', 'node3'])
    yield
    mock_store.reset()


@pytest.fixture
def mock_object_storage(monkeypatch):
    """Monkeypatch object storage with mock implementation"""
    from tests.mocks import mock_object_store
    
    # Adapt the mock functions to match actual signatures
    def mock_write_adapter(checksum, data, nodes):
        for node in nodes:
            mock_object_store.mock_write_chunk(checksum, data, node)
    
    def mock_read_adapter(checksum, nodes):
        for node in nodes:
            try:
                return mock_object_store.mock_read_chunk(checksum, node)
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"Chunk {checksum} not found")
    
    def mock_delete_adapter(checksum, nodes):
        for node in nodes:
            try:
                mock_object_store.mock_delete_chunk(checksum, node)
            except FileNotFoundError:
                pass
    
    monkeypatch.setattr('data.services.object_store.write_chunk', mock_write_adapter)
    monkeypatch.setattr('data.services.object_store.read_chunk', mock_read_adapter)
    monkeypatch.setattr('data.services.object_store.delete_chunk', mock_delete_adapter)
    monkeypatch.setattr('data.services.object_store._chunk_path', mock_object_store.mock_chunk_path)
    
    return mock_object_store.mock_store


@pytest.fixture
def api_client():
    """DRF API client"""
    return APIClient()


@pytest.fixture
def user_factory():
    """Factory for creating test users"""
    def create_user(username='testuser', email='test@example.com', password='testpass123'):
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        UserQuota.objects.get_or_create(
            user=user,
            defaults={'storage_limit_bytes': 5 * 1024 * 1024 * 1024}
        )
        return user
    return create_user


@pytest.fixture
def authenticated_client(api_client, user_factory):
    """API client with authenticated user"""
    user = user_factory()
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    api_client.user = user
    return api_client


@pytest.fixture
def test_file_factory():
    """Factory for creating test file content"""
    def create_file(size_bytes=1024, content=None):
        if content is None:
            content = b'X' * size_bytes
        return io.BytesIO(content)
    return create_file


@pytest.fixture
def chunk_factory():
    """Factory for creating test chunks"""
    def create_chunk(checksum=None, size_bytes=256*1024, ref_count=1, storage_nodes=None):
        if checksum is None:
            import hashlib
            checksum = hashlib.sha256(b'test_data').hexdigest()
        if storage_nodes is None:
            storage_nodes = ['node1', 'node2', 'node3']
        
        chunk = ObjectChunk.objects.create(
            checksum=checksum,
            size_bytes=size_bytes,
            ref_count=ref_count,
            storage_nodes=storage_nodes
        )
        return chunk
    return create_chunk


@pytest.fixture
def stored_file_factory(user_factory):
    """Factory for creating stored files"""
    def create_stored_file(user=None, filename='test.txt', size_bytes=1024):
        if user is None:
            user = user_factory()
        
        stored_file = StoredFile.objects.create(
            owner=user,
            filename=filename,
            size_bytes=size_bytes,
            file_checksum='a' * 64
        )
        return stored_file
    return create_stored_file


@pytest.fixture
def disable_rate_limiting(monkeypatch):
    """Disable rate limiting for tests"""
    def mock_sliding_window(limit, window_sec):
        def decorator(view_func):
            return view_func
        return decorator
    
    monkeypatch.setattr('data.services.rate_limiter.sliding_window', mock_sliding_window)


@pytest.fixture
def celery_eager(settings):
    """Configure Celery to run tasks synchronously"""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
