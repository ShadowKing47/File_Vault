"""
Mock object storage implementation for testing.
Replaces disk I/O with in-memory operations.
"""
import hashlib
from typing import List, Dict
from pathlib import Path


class MockObjectStore:
    """In-memory mock object storage"""
    
    def __init__(self):
        self.storage: Dict[str, Dict[str, bytes]] = {}
        self.nodes = []
        self.failed_nodes = set()
    
    def reset(self):
        """Clear all stored data"""
        self.storage.clear()
        self.failed_nodes.clear()
    
    def set_nodes(self, nodes: List[str]):
        """Set available storage nodes"""
        self.nodes = nodes
        for node in nodes:
            if node not in self.storage:
                self.storage[node] = {}
    
    def simulate_node_failure(self, node: str):
        """Simulate a node being unavailable"""
        self.failed_nodes.add(node)
    
    def restore_node(self, node: str):
        """Restore a failed node"""
        self.failed_nodes.discard(node)
    
    def write_chunk(self, checksum: str, data: bytes, nodes: List[str]) -> None:
        """Write chunk to specified nodes"""
        for node in nodes:
            if node in self.failed_nodes:
                continue
            if node not in self.storage:
                self.storage[node] = {}
            self.storage[node][checksum] = data
    
    def read_chunk(self, checksum: str, nodes: List[str]) -> bytes:
        """Read chunk from any available node"""
        for node in nodes:
            if node in self.failed_nodes:
                continue
            if node in self.storage and checksum in self.storage[node]:
                return self.storage[node][checksum]
        raise FileNotFoundError(f"Chunk {checksum[:12]} not found on any node")
    
    def delete_chunk(self, checksum: str, nodes: List[str]) -> None:
        """Delete chunk from all nodes"""
        for node in nodes:
            if node in self.storage and checksum in self.storage[node]:
                del self.storage[node][checksum]
    
    def chunk_exists(self, checksum: str, node: str) -> bool:
        """Check if chunk exists on specific node"""
        return node in self.storage and checksum in self.storage[node]
    
    def get_node_chunks(self, node: str) -> List[str]:
        """Get all chunk checksums on a node"""
        if node in self.storage:
            return list(self.storage[node].keys())
        return []
    
    def _chunk_path(self, node: str, checksum: str) -> str:
        """Mock chunk path for compatibility"""
        sub1 = checksum[:2]
        sub2 = checksum[2:4]
        return f"{node}/{sub1}/{sub2}/{checksum}"


# Global mock instance
mock_store = MockObjectStore()


def mock_write_chunk(checksum: str, data: bytes, nodes: List[str]) -> None:
    """Mock write_chunk function"""
    mock_store.write_chunk(checksum, data, nodes)


def mock_read_chunk(checksum: str, nodes: List[str]) -> bytes:
    """Mock read_chunk function"""
    return mock_store.read_chunk(checksum, nodes)


def mock_delete_chunk(checksum: str, nodes: List[str]) -> None:
    """Mock delete_chunk function"""
    mock_store.delete_chunk(checksum, nodes)


def mock_chunk_path(node: str, checksum: str) -> str:
    """Mock _chunk_path function"""
    return mock_store._chunk_path(node, checksum)
