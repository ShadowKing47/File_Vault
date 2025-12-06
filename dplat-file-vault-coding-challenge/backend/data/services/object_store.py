import logging
import os
from pathlib import Path
from typing import List
import random

from django.conf import settings

logger = logging.getLogger(__name__)

NODES = getattr(settings, "OBJECT_STORAGE_NODES", [])


def _ensure_node_dirs():
    for node in NODES:
        Path(node).mkdir(parents=True, exist_ok=True)


def _chunk_path(node: str, checksum: str) -> str:
    sub1 = checksum[:2]
    sub2 = checksum[2:4]
    dir_path = Path(node) / sub1 / sub2
    dir_path.mkdir(parents=True, exist_ok=True)
    return str(dir_path / checksum)


def choose_storage_nodes(replication_factor: int = 3) -> List[str]:
    """Choose random storage nodes for chunk replication"""
    if len(NODES) < replication_factor:
        error_msg = f"Not enough storage nodes configured. Needed {replication_factor}, have {len(NODES)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    selected = random.sample(NODES, replication_factor)
    logger.debug(f"Selected storage nodes: {selected}")
    return selected


def write_chunk(checksum: str, data: bytes, nodes: List[str]) -> None:
    """Write chunk data to multiple storage nodes"""
    _ensure_node_dirs()
    written_count = 0
    for node in nodes:
        try:
            path = _chunk_path(node, checksum)
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(data)
                written_count += 1
                logger.debug(f"Chunk written to node", extra={"checksum": checksum[:12], "node": node})
        except Exception as e:
            logger.error(
                f"Failed to write chunk to node",
                extra={"checksum": checksum[:12], "node": node, "error": str(e)}
            )
    logger.info(f"Chunk written to {written_count}/{len(nodes)} nodes", extra={"checksum": checksum[:12]})


def read_chunk(checksum: str, nodes: List[str]) -> bytes:
    """Read chunk data from storage nodes"""
    for node in nodes:
        path = _chunk_path(node, checksum)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    data = f.read()
                logger.debug(f"Chunk read from node", extra={"checksum": checksum[:12], "node": node})
                return data
            except Exception as e:
                logger.warning(
                    f"Failed to read chunk from node",
                    extra={"checksum": checksum[:12], "node": node, "error": str(e)}
                )
                continue
    error_msg = f"Chunk {checksum[:12]} not found on any node"
    logger.error(error_msg, extra={"nodes": nodes})
    raise FileNotFoundError(error_msg)


def delete_chunk(checksum: str, nodes: List[str]) -> None:
    """Delete chunk from all storage nodes"""
    deleted_count = 0
    for node in nodes:
        path = _chunk_path(node, checksum)
        try:
            os.remove(path)
            deleted_count += 1
            logger.debug(f"Chunk deleted from node", extra={"checksum": checksum[:12], "node": node})
        except FileNotFoundError:
            logger.debug(f"Chunk not found on node", extra={"checksum": checksum[:12], "node": node})
        except Exception as e:
            logger.error(
                f"Failed to delete chunk from node",
                extra={"checksum": checksum[:12], "node": node, "error": str(e)}
            )
    logger.info(f"Chunk deleted from {deleted_count}/{len(nodes)} nodes", extra={"checksum": checksum[:12]})
