# File Vault

A Django-based distributed object storage system with advanced features including file chunking, deduplication, user quotas, and rate limiting. Architected an S3-style storage backend with block-level deduplication, chunk replication, and a custom object store. A secure upload/download pipelines with user quota enforcement, Redis sliding-window rate limiting, and Celery-driven replication, GC, and node health checks

## Features

- **Distributed Object Storage**: Files are split into chunks and distributed across multiple storage nodes
- **Content-Addressable Storage**: Chunks are identified by SHA-256 checksums for deduplication
- **Automatic Deduplication**: Identical chunks are stored only once, saving storage space
- **User Quotas**: Per-user storage limits with automatic quota tracking (default 5GB)
- **Rate Limiting**: Configurable request rate limiting using Redis sliding window algorithm
- **Reference Counting**: Automatic garbage collection of unused chunks
- **File Filtering & Search**: Advanced filtering by filename, size, and modification date
- **Comprehensive Logging**: Detailed logging at all endpoints for debugging and monitoring

## Technology Stack

### Backend
- Django 4.x (Python web framework)
- Django REST Framework (API development)
- SQLite (Development database)
- Redis (Rate limiting & Celery broker)
- Celery (Asynchronous task queue for maintenance)
- Gunicorn (WSGI HTTP Server)
- WhiteNoise (Static file serving)
- Django Filter (Advanced query filtering)

### Infrastructure
- Docker and Docker Compose
- Multi-node distributed storage with replication (3x default)
- Chunked storage with configurable chunk size (256KB default)
- Background workers for replication and garbage collection

## Prerequisites

Before you begin, ensure you have installed:
- Docker (20.10.x or higher) and Docker Compose (2.x or higher)
- Python (3.9 or higher) - for local development
- Redis (6.x or higher) - for rate limiting and Celery (required)
