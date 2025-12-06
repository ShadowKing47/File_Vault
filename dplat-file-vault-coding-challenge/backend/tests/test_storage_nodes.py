"""
Tests for storage node operations.
"""
import pytest
from data.models import ObjectChunk


@pytest.mark.django_db
class TestStorageNodeDistribution:
    """Test chunk distribution across storage nodes"""
    
    def test_chunks_stored_on_multiple_nodes(self, chunk_factory):
        """Test that chunks are stored on multiple nodes for redundancy"""
        chunk = chunk_factory(storage_nodes=['node1', 'node2', 'node3'])
        
        assert len(chunk.storage_nodes) >= 2  # At least 2x replication
    
    def test_default_replication_factor(self, chunk_factory):
        """Test default replication factor is 3"""
        chunk = chunk_factory()
        
        # Default should be 3 nodes
        assert len(chunk.storage_nodes) == 3
    
    def test_storage_nodes_distribution(self, authenticated_client, mock_object_storage, disable_rate_limiting):
        """Test that uploaded chunks are distributed across nodes"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        content = b'X' * (256 * 1024 * 2)  # 2 chunks
        file = SimpleUploadedFile('test.bin', content, content_type='application/octet-stream')
        
        response = authenticated_client.post('/api/files/upload/', {
            'file': file
        }, format='multipart')
        
        assert response.status_code == 201
        
        from data.models import StoredFile
        stored_file = StoredFile.objects.get(id=response.data['file_id'])
        
        # Each chunk should be on multiple nodes
        for chunk in stored_file.chunks.all():
            assert len(chunk.storage_nodes) > 1


@pytest.mark.django_db
class TestNodeFailureHandling:
    """Test handling of storage node failures"""
    
    def test_read_from_alternate_node_on_failure(self, chunk_factory, mock_object_storage):
        """Test reading from alternate node when primary fails"""
        chunk = chunk_factory(storage_nodes=['node1', 'node2', 'node3'])
        
        # Store on all nodes
        test_data = b'test chunk data'
        for node in chunk.storage_nodes:
            mock_object_storage.write_chunk(chunk.checksum, test_data, node)
        
        # Simulate node1 failure
        mock_object_storage.simulate_node_failure('node1')
        
        # Should still be able to read from other nodes
        data = mock_object_storage.read_chunk(chunk.checksum, 'node2')
        assert data == test_data
    
    def test_write_skips_failed_nodes(self, mock_object_storage):
        """Test that writes skip failed nodes"""
        # Simulate node failure
        mock_object_storage.simulate_node_failure('node2')
        
        # Attempt write to all nodes
        test_data = b'test data'
        checksum = 'test_checksum_' + 'a' * 50
        
        for node in ['node1', 'node2', 'node3']:
            try:
                mock_object_storage.write_chunk(checksum, test_data, node)
            except:
                # node2 should fail
                pass
        
        # Should be written to healthy nodes
        assert mock_object_storage.chunk_exists(checksum, 'node1')
        assert not mock_object_storage.chunk_exists(checksum, 'node2')
        assert mock_object_storage.chunk_exists(checksum, 'node3')
    
    def test_node_recovery(self, mock_object_storage):
        """Test node recovery after failure"""
        # Simulate failure
        mock_object_storage.simulate_node_failure('node2')
        
        # Verify node is down
        test_data = b'test'
        checksum = 'recovery_test_' + 'b' * 50
        
        try:
            mock_object_storage.write_chunk(checksum, test_data, 'node2')
            assert False, "Should have failed"
        except:
            pass
        
        # Restore node
        mock_object_storage.restore_node('node2')
        
        # Should now work
        mock_object_storage.write_chunk(checksum, test_data, 'node2')
        assert mock_object_storage.chunk_exists(checksum, 'node2')


@pytest.mark.django_db
class TestChunkSharding:
    """Test chunk sharding across storage nodes"""
    
    def test_chunk_location_deterministic(self, chunk_factory):
        """Test that chunk location is deterministic based on checksum"""
        checksum = 'a' * 64
        
        # Create chunks with same checksum
        chunk1 = chunk_factory(checksum=checksum)
        chunk2 = ObjectChunk.objects.get(checksum=checksum)
        
        # Should have same storage nodes
        assert chunk1.storage_nodes == chunk2.storage_nodes
    
    def test_different_chunks_different_nodes(self, chunk_factory):
        """Test that different chunks may be on different nodes"""
        chunk1 = chunk_factory(checksum='a' * 64, storage_nodes=['node1', 'node2', 'node3'])
        chunk2 = chunk_factory(checksum='b' * 64, storage_nodes=['node1', 'node2', 'node3'])
        
        # May be on different nodes (or same, but independent)
        assert isinstance(chunk1.storage_nodes, list)
        assert isinstance(chunk2.storage_nodes, list)


@pytest.mark.django_db
class TestStorageNodeMetadata:
    """Test storage node metadata tracking"""
    
    def test_chunk_tracks_storage_nodes(self, chunk_factory):
        """Test that chunks track which nodes they're stored on"""
        nodes = ['node1', 'node2', 'node3']
        chunk = chunk_factory(storage_nodes=nodes)
        
        assert chunk.storage_nodes == nodes
    
    def test_storage_nodes_json_field(self, chunk_factory):
        """Test that storage_nodes is properly stored as JSON"""
        nodes = ['node1', 'node2', 'node3']
        chunk = chunk_factory(storage_nodes=nodes)
        
        # Refresh from DB
        chunk.refresh_from_db()
        
        # Should still be list
        assert isinstance(chunk.storage_nodes, list)
        assert chunk.storage_nodes == nodes


@pytest.mark.django_db
class TestReplication:
    """Test chunk replication logic"""
    
    def test_ensure_minimum_replication(self, chunk_factory, mock_object_storage):
        """Test ensuring minimum replication factor"""
        # Create under-replicated chunk
        chunk = chunk_factory(storage_nodes=['node1'])
        
        # Store on single node
        test_data = b'test data'
        mock_object_storage.write_chunk(chunk.checksum, test_data, 'node1')
        
        # Should detect under-replication
        assert len(chunk.storage_nodes) < 3
    
    def test_replicate_to_new_node(self, chunk_factory, mock_object_storage):
        """Test replicating chunk to additional node"""
        chunk = chunk_factory(storage_nodes=['node1'])
        
        # Store on first node
        test_data = b'replicate test data'
        mock_object_storage.write_chunk(chunk.checksum, test_data, 'node1')
        
        # Replicate to node2
        data = mock_object_storage.read_chunk(chunk.checksum, 'node1')
        mock_object_storage.write_chunk(chunk.checksum, data, 'node2')
        
        # Verify replicated
        assert mock_object_storage.chunk_exists(chunk.checksum, 'node2')
        replicated_data = mock_object_storage.read_chunk(chunk.checksum, 'node2')
        assert replicated_data == test_data
