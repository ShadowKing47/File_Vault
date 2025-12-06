"""
Tests for file chunk operations.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from data.models import FileChunk
import hashlib


@pytest.mark.django_db
class TestChunkSequencing:
    """Test chunk sequencing and ordering"""
    
    def test_chunk_index_starts_at_zero(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that chunk indexing starts at 0"""
        chunk_size = 256 * 1024
        content = b'A' * chunk_size + b'B' * 100
        
        file = SimpleUploadedFile('indexed.bin', content, content_type='application/octet-stream')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        file_chunks = FileChunk.objects.filter(stored_file=stored_file).order_by('chunk_index')
        indices = [fc.chunk_index for fc in file_chunks]
        
        # Should start at 0
        assert indices[0] == 0
        # Should be sequential
        assert indices == list(range(len(indices)))
    
    def test_chunk_order_preserved(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that chunk order is preserved"""
        chunk_size = 256 * 1024
        content = b'A' * chunk_size + b'B' * chunk_size + b'C' * 1000
        
        file = SimpleUploadedFile('ordered.bin', content, content_type='application/octet-stream')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        file_chunks = FileChunk.objects.filter(stored_file=stored_file).order_by('chunk_index')
        
        # Verify correct number of chunks
        assert len(file_chunks) == 3
        
        # Verify indices are sequential
        for i, fc in enumerate(file_chunks):
            assert fc.chunk_index == i
    
    def test_single_chunk_file(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test file smaller than chunk size"""
        content = b'Small file'
        file = SimpleUploadedFile('small.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        file_chunks = FileChunk.objects.filter(stored_file=stored_file)
        
        # Should be exactly 1 chunk
        assert len(file_chunks) == 1
        assert file_chunks[0].chunk_index == 0


@pytest.mark.django_db
class TestChunkChecksums:
    """Test chunk checksum calculation"""
    
    def test_chunk_checksum_sha256(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that chunks use SHA256 checksums"""
        content = b'Test content for checksum'
        file = SimpleUploadedFile('checksum.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        chunk = stored_file.chunks.first()
        
        # Should be 64 hex characters (SHA256)
        assert len(chunk.checksum) == 64
        assert all(c in '0123456789abcdef' for c in chunk.checksum)
    
    def test_identical_content_same_checksum(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that identical content produces same checksum"""
        content = b'Identical content'
        
        # Upload first file
        file1 = SimpleUploadedFile('file1.txt', content, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        
        # Upload second file with same content
        file2 = SimpleUploadedFile('file2.txt', content, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
        stored_file2 = StoredFile.objects.get(id=response2.data['file_id'])
        
        chunk1 = stored_file1.chunks.first()
        chunk2 = stored_file2.chunks.first()
        
        # Should have same checksum
        assert chunk1.checksum == chunk2.checksum
    
    def test_different_content_different_checksum(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that different content produces different checksums"""
        content1 = b'Content one'
        content2 = b'Content two'
        
        file1 = SimpleUploadedFile('file1.txt', content1, content_type='text/plain')
        response1 = authenticated_client.post('/api/files/upload/', {
            'file': file1
        }, format='multipart')
        
        file2 = SimpleUploadedFile('file2.txt', content2, content_type='text/plain')
        response2 = authenticated_client.post('/api/files/upload/', {
            'file': file2
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file1 = StoredFile.objects.get(id=response1.data['file_id'])
        stored_file2 = StoredFile.objects.get(id=response2.data['file_id'])
        
        chunk1 = stored_file1.chunks.first()
        chunk2 = stored_file2.chunks.first()
        
        # Should have different checksums
        assert chunk1.checksum != chunk2.checksum
    
    def test_checksum_matches_actual_hash(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that stored checksum matches actual SHA256 hash"""
        content = b'Content for hash verification'
        expected_hash = hashlib.sha256(content).hexdigest()
        
        file = SimpleUploadedFile('verify.txt', content, content_type='text/plain')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        chunk = stored_file.chunks.first()
        
        # Stored checksum should match computed hash
        assert chunk.checksum == expected_hash


@pytest.mark.django_db
class TestChunkBoundaries:
    """Test chunk boundary handling"""
    
    def test_exact_chunk_size_boundary(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test file that is exactly chunk_size"""
        chunk_size = 256 * 1024
        content = b'X' * chunk_size
        
        file = SimpleUploadedFile('exact.bin', content, content_type='application/octet-stream')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        file_chunks = FileChunk.objects.filter(stored_file=stored_file)
        
        # Should be exactly 1 chunk
        assert len(file_chunks) == 1
    
    def test_chunk_size_plus_one(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test file that is chunk_size + 1"""
        chunk_size = 256 * 1024
        content = b'X' * (chunk_size + 1)
        
        file = SimpleUploadedFile('plus_one.bin', content, content_type='application/octet-stream')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        file_chunks = FileChunk.objects.filter(stored_file=stored_file)
        
        # Should be 2 chunks (one full, one with 1 byte)
        assert len(file_chunks) == 2
    
    def test_partial_last_chunk(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that last chunk can be partial"""
        chunk_size = 256 * 1024
        content = b'A' * chunk_size + b'B' * 1000
        
        file = SimpleUploadedFile('partial.bin', content, content_type='application/octet-stream')
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        file_chunks = FileChunk.objects.filter(stored_file=stored_file).order_by('chunk_index')
        
        assert len(file_chunks) == 2
        
        # First chunk should be full size
        assert file_chunks[0].chunk.size_bytes == chunk_size
        # Last chunk should be partial
        assert file_chunks[1].chunk.size_bytes == 1000


@pytest.mark.django_db
class TestChunkMetadata:
    """Test chunk metadata"""
    
    def test_chunk_size_tracked(self, chunk_factory):
        """Test that chunk size is tracked"""
        size = 123456
        chunk = chunk_factory(size_bytes=size)
        
        assert chunk.size_bytes == size
    
    def test_chunk_ref_count_initialized(self, chunk_factory):
        """Test that ref_count is initialized correctly"""
        chunk = chunk_factory(ref_count=1)
        
        assert chunk.chunk.ref_count == 1
    
    def test_file_chunk_relationship(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test FileChunk relationship between StoredFile and ObjectChunk"""
        content = b'Test relationship'
        file = SimpleUploadedFile('rel.txt', content, content_type='text/plain')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        file_chunk = FileChunk.objects.get(stored_file=stored_file)
        
        # Should link to stored file
        assert file_chunk.stored_file == stored_file
        # Should link to object chunk
        assert file_chunk.chunk is not None
        # Should have index
        assert file_chunk.chunk_index == 0
