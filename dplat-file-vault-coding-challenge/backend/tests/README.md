# Test Suite

Comprehensive test suite for the file vault distributed storage system.

## Test Structure

### Core Functionality Tests (12 modules)
- `test_auth.py` - Authentication and JWT token management
- `test_upload.py` - File upload functionality and chunking
- `test_dedup.py` - Deduplication and chunk sharing
- `test_quota.py` - User quota tracking and enforcement
- `test_download.py` - File download and streaming
- `test_delete.py` - File deletion and reference counting
- `test_gc.py` - Garbage collection of orphaned chunks
- `test_search.py` - File search, filtering, and listing
- `test_rate_limit.py` - Rate limiting enforcement
- `test_storage_nodes.py` - Storage node operations and distribution
- `test_file_chunks.py` - Chunk sequencing and metadata
- `test_user_profile.py` - User profile and password management

### Advanced Tests
- `test_celery_integration.py` - Celery task execution and periodic scheduling
- `test_stress.py` - Concurrent operations, large files, high volume
- `test_property_based.py` - Property-based tests with Hypothesis

### Mocks
- `mocks/mock_object_store.py` - In-memory mock object storage

## Running Tests

### All tests
```bash
pytest
```

### Specific module
```bash
pytest tests/test_upload.py
```

### Specific test class
```bash
pytest tests/test_upload.py::TestFileUpload
```

### Specific test
```bash
pytest tests/test_upload.py::TestFileUpload::test_upload_small_file
```

### With coverage
```bash
pytest --cov=data --cov=files --cov-report=html
```

### Parallel execution
```bash
pytest -n auto
```

### Verbose output
```bash
pytest -v
```

## Test Configuration

Tests use:
- **pytest-django**: Django integration
- **DRF APIClient**: REST API testing
- **Hypothesis**: Property-based testing
- **Mock object storage**: In-memory storage (no disk I/O)
- **Fixtures**: User factories, authenticated clients, test data generators

## Fixtures (conftest.py)

### Database & Storage
- `enable_db_access_for_all_tests` - Enable DB access
- `reset_mock_storage` - Reset mock storage between tests
- `mock_object_storage` - Monkeypatched object storage

### Clients
- `api_client` - Unauthenticated API client
- `authenticated_client` - API client with JWT token

### Factories
- `user_factory` - Create test users with quotas
- `chunk_factory` - Create test chunks
- `stored_file_factory` - Create test files
- `test_file_factory` - Generate test file content

### Configuration
- `disable_rate_limiting` - Disable rate limiting for tests
- `celery_eager` - Run Celery tasks synchronously

## Test Categories

### Unit Tests
Test individual components in isolation:
- Model methods
- Serializer validation
- Utility functions
- Checksum calculations

### Integration Tests
Test component interactions:
- File upload → chunking → deduplication
- File delete → ref_count update → GC
- User registration → quota creation
- Upload → quota enforcement

### Stress Tests
Test system under load:
- Concurrent uploads from multiple users
- Large files (10MB, 50MB)
- High volume operations (100+ files)
- Rapid upload/delete cycles

### Property-Based Tests
Test invariants with generated data:
- Checksum determinism
- Ref count calculations
- Quota arithmetic
- Chunk reconstruction

## Coverage Goals

Target: **90%+ code coverage**

Critical paths requiring 100% coverage:
- File upload chunking logic
- Deduplication detection
- Reference count management
- Quota enforcement
- Authentication flows

## Test Best Practices

1. **Use factories** - Don't create test data manually
2. **Mock external dependencies** - Use mock object storage
3. **Test edge cases** - Empty files, exact chunk boundaries, quota limits
4. **Test error paths** - Invalid inputs, unauthorized access, quota exceeded
5. **Test concurrency** - Race conditions, simultaneous operations
6. **Verify cleanup** - Check ref_counts, storage deletion, quota updates
7. **Test determinism** - Same input → same output

## Common Test Patterns

### Upload test pattern
```python
file = SimpleUploadedFile('test.txt', b'content', content_type='text/plain')
response = authenticated_client.post('/api/data/upload/', {'file': file}, format='multipart')
assert response.status_code == 201
```

### Dedup verification
```python
# Upload same content twice
file1 = SimpleUploadedFile('f1.txt', content, ...)
response1 = client.post('/api/data/upload/', {'file': file1}, ...)

file2 = SimpleUploadedFile('f2.txt', content, ...)
response2 = client.post('/api/data/upload/', {'file': file2}, ...)

# Verify same chunks used
stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
stored_file2 = StoredFile.objects.get(id=response2.data['file_id'])

chunks1 = list(stored_file1.chunks.all())
chunks2 = list(stored_file2.chunks.all())

assert chunks1[0].checksum == chunks2[0].checksum
assert chunks1[0].ref_count == 2
```

### Quota check pattern
```python
quota = UserQuota.objects.get(user=authenticated_client.user)
initial_usage = quota.storage_used_bytes

# Perform operation

quota.refresh_from_db()
assert quota.storage_used_bytes == initial_usage + expected_change
```

## Troubleshooting

### Tests fail with "database locked"
Use `pytest -n auto` with `pytest-xdist` or run tests serially

### Mock storage not resetting
Check `reset_mock_storage` fixture is being used

### Rate limiting causing failures
Use `disable_rate_limiting` fixture

### Celery tasks not running
Use `celery_eager` fixture for synchronous execution

## CI/CD Integration

Recommended GitHub Actions workflow:
```yaml
- name: Run tests
  run: |
    pytest --cov=data --cov=files --cov-report=xml --cov-report=term
```
