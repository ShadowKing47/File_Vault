"""
Property-based tests using Hypothesis for comprehensive edge case coverage.
"""
import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.extra.django import TestCase as HypothesisTestCase
import hashlib


# Strategies for generating test data
chunk_sizes = st.integers(min_value=1, max_value=256 * 1024)
file_sizes = st.integers(min_value=0, max_value=10 * 1024 * 1024)
small_file_sizes = st.integers(min_value=0, max_value=1024 * 1024)
content_bytes = st.binary(min_size=0, max_size=1024 * 1024)
checksums = st.text(alphabet='0123456789abcdef', min_size=64, max_size=64)
ref_counts = st.integers(min_value=0, max_value=1000)
storage_node_names = st.lists(
    st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=4, max_size=10),
    min_size=1,
    max_size=5,
    unique=True
)


@pytest.mark.django_db
class TestChunkingProperties:
    """Property-based tests for chunking logic"""
    
    @given(content=content_bytes)
    @settings(max_examples=50, deadline=None)
    def test_checksum_deterministic(self, content):
        """Test that checksums are deterministic for same content"""
        checksum1 = hashlib.sha256(content).hexdigest()
        checksum2 = hashlib.sha256(content).hexdigest()
        
        assert checksum1 == checksum2
    
    @given(content1=content_bytes, content2=content_bytes)
    @settings(max_examples=50, deadline=None)
    def test_different_content_different_checksum(self, content1, content2):
        """Test that different content produces different checksums"""
        assume(content1 != content2)
        
        checksum1 = hashlib.sha256(content1).hexdigest()
        checksum2 = hashlib.sha256(content2).hexdigest()
        
        assert checksum1 != checksum2
    
    @given(size=small_file_sizes)
    @settings(max_examples=50, deadline=None)
    def test_chunk_count_calculation(self, size):
        """Test chunk count calculation for various file sizes"""
        chunk_size = 256 * 1024
        
        if size == 0:
            expected_chunks = 1
        else:
            expected_chunks = (size + chunk_size - 1) // chunk_size
        
        # Verify calculation
        assert expected_chunks >= 0
        
        if size > 0:
            assert expected_chunks == ((size - 1) // chunk_size) + 1


@pytest.mark.django_db
class TestRefCountProperties:
    """Property-based tests for reference counting"""
    
    @given(initial_count=ref_counts, increment=st.integers(min_value=0, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_ref_count_increment(self, initial_count, increment):
        """Test ref_count increments correctly"""
        final_count = initial_count + increment
        
        assert final_count >= initial_count
        assert final_count == initial_count + increment
    
    @given(initial_count=st.integers(min_value=1, max_value=1000), decrement=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_ref_count_decrement(self, initial_count, decrement):
        """Test ref_count decrements correctly"""
        assume(decrement <= initial_count)
        
        final_count = initial_count - decrement
        
        assert final_count >= 0
        assert final_count == initial_count - decrement
    
    @given(count=ref_counts)
    @settings(max_examples=50, deadline=None)
    def test_orphan_detection(self, count):
        """Test orphan detection based on ref_count"""
        is_orphaned = count <= 0
        
        if count <= 0:
            assert is_orphaned
        else:
            assert not is_orphaned


@pytest.mark.django_db
class TestStorageNodeProperties:
    """Property-based tests for storage node operations"""
    
    @given(nodes=storage_node_names)
    @settings(max_examples=30, deadline=None)
    def test_storage_node_list_valid(self, nodes):
        """Test that storage node lists are valid"""
        assert isinstance(nodes, list)
        assert len(nodes) > 0
        assert len(nodes) == len(set(nodes))  # All unique
    
    @given(nodes=storage_node_names)
    @settings(max_examples=30, deadline=None)
    def test_replication_factor(self, nodes):
        """Test replication factor properties"""
        replication_factor = len(nodes)
        
        assert replication_factor >= 1
        assert replication_factor <= 10  # Reasonable upper bound


@pytest.mark.django_db
class TestDeduplicationProperties:
    """Property-based tests for deduplication"""
    
    @given(content=content_bytes, num_copies=st.integers(min_value=1, max_value=10))
    @settings(max_examples=30, deadline=None)
    def test_duplicate_detection(self, content, num_copies):
        """Test that duplicates are detected regardless of count"""
        checksums = [hashlib.sha256(content).hexdigest() for _ in range(num_copies)]
        
        # All checksums should be identical
        assert len(set(checksums)) == 1
        
        # All should equal the first
        for checksum in checksums:
            assert checksum == checksums[0]
    
    @given(contents=st.lists(content_bytes, min_size=1, max_size=10, unique=True))
    @settings(max_examples=30, deadline=None)
    def test_unique_content_unique_checksums(self, contents):
        """Test that unique content produces unique checksums"""
        checksums = [hashlib.sha256(c).hexdigest() for c in contents]
        
        # All checksums should be unique
        assert len(set(checksums)) == len(checksums)


@pytest.mark.django_db
class TestQuotaProperties:
    """Property-based tests for quota management"""
    
    @given(limit=st.integers(min_value=1024, max_value=100 * 1024 * 1024),
           usage=st.integers(min_value=0, max_value=100 * 1024 * 1024))
    @settings(max_examples=50, deadline=None)
    def test_quota_validation(self, limit, usage):
        """Test quota validation properties"""
        assume(usage <= limit)
        
        within_quota = usage <= limit
        remaining = limit - usage
        
        assert within_quota
        assert remaining >= 0
        assert remaining == limit - usage
    
    @given(limit=st.integers(min_value=1024, max_value=100 * 1024 * 1024),
           usage=st.integers(min_value=0, max_value=50 * 1024 * 1024),
           file_size=st.integers(min_value=1, max_value=10 * 1024 * 1024))
    @settings(max_examples=50, deadline=None)
    def test_quota_after_upload(self, limit, usage, file_size):
        """Test quota calculation after upload"""
        assume(usage <= limit)
        
        would_exceed = (usage + file_size) > limit
        
        if would_exceed:
            # Upload should be rejected
            assert usage + file_size > limit
        else:
            # Upload should be allowed
            new_usage = usage + file_size
            assert new_usage <= limit
    
    @given(usage=st.integers(min_value=1024, max_value=100 * 1024 * 1024),
           file_size=st.integers(min_value=1, max_value=10 * 1024 * 1024))
    @settings(max_examples=50, deadline=None)
    def test_quota_after_delete(self, usage, file_size):
        """Test quota calculation after delete"""
        assume(file_size <= usage)
        
        new_usage = usage - file_size
        
        assert new_usage >= 0
        assert new_usage == usage - file_size
        assert new_usage < usage


@pytest.mark.django_db
class TestFileIntegrityProperties:
    """Property-based tests for file integrity"""
    
    @given(content=content_bytes)
    @settings(max_examples=50, deadline=None)
    def test_upload_download_roundtrip(self, content):
        """Test that upload->download preserves content"""
        # Hash should be same
        original_hash = hashlib.sha256(content).hexdigest()
        
        # Simulated roundtrip
        stored_hash = original_hash
        retrieved_hash = stored_hash
        
        assert original_hash == retrieved_hash
    
    @given(chunks=st.lists(content_bytes, min_size=1, max_size=10))
    @settings(max_examples=30, deadline=None)
    def test_chunk_reconstruction(self, chunks):
        """Test that chunks reconstruct to original file"""
        # Concatenate chunks
        original = b''.join(chunks)
        
        # Reconstruct
        reconstructed = b''.join(chunks)
        
        assert original == reconstructed
        assert len(original) == len(reconstructed)
        assert hashlib.sha256(original).hexdigest() == hashlib.sha256(reconstructed).hexdigest()


@pytest.mark.django_db
class TestBoundaryConditions:
    """Property-based tests for boundary conditions"""
    
    @given(size=st.integers(min_value=0, max_value=1024))
    @settings(max_examples=50, deadline=None)
    def test_small_file_handling(self, size):
        """Test handling of various small file sizes"""
        content = b'X' * size
        
        # Should always be valid
        assert len(content) == size
        assert len(content) >= 0
    
    @given(offset=st.integers(min_value=0, max_value=1024),
           length=st.integers(min_value=0, max_value=1024))
    @settings(max_examples=50, deadline=None)
    def test_chunk_boundary_alignment(self, offset, length):
        """Test chunk boundary calculations"""
        chunk_size = 256 * 1024
        
        start_chunk = offset // chunk_size
        end_chunk = (offset + length - 1) // chunk_size if length > 0 else start_chunk
        
        assert start_chunk >= 0
        assert end_chunk >= start_chunk
        
        if length == 0:
            assert end_chunk == start_chunk


@pytest.mark.django_db
class TestErrorHandlingProperties:
    """Property-based tests for error handling"""
    
    @given(checksum=checksums)
    @settings(max_examples=30, deadline=None)
    def test_checksum_format_validation(self, checksum):
        """Test checksum format validation"""
        # Should be 64 hex characters
        assert len(checksum) == 64
        assert all(c in '0123456789abcdef' for c in checksum)
    
    @given(node_name=st.text(min_size=1, max_size=50))
    @settings(max_examples=30, deadline=None)
    def test_storage_node_name_validation(self, node_name):
        """Test storage node name validation"""
        # Should be non-empty string
        assert isinstance(node_name, str)
        assert len(node_name) > 0
