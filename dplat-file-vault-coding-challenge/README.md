# Abnormal File Vault

A Django-based distributed object storage system with advanced features including file chunking, deduplication, user quotas, and rate limiting.

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

## 🛠️ Installation & Setup

### Using Docker (Recommended)

```bash
docker-compose up --build
```

### Local Development Setup

#### Backend Setup
1. **Create and activate virtual environment**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create necessary directories**
   ```bash
   mkdir -p media staticfiles data logs
   mkdir -p object_store_node1 object_store_node2 object_store_node3
   ```

4. **Run migrations**
   ```bash
   python manage.py migrate
   ```

5. **Start the development server**
   ```bash
   python manage.py runserver
   ```

6. **Start Celery workers (for background tasks)**
   ```bash
   # In a separate terminal
   celery -A core worker --beat --loglevel=info --pool=solo
   
   # Or use the provided script
   ./start_celery.ps1  # Windows
   ./start_celery.sh   # Linux/Mac
   ```

## Background Tasks & Maintenance

The system includes Celery workers for automated maintenance:

- **Replication Check**: Ensures all chunks are properly replicated (runs hourly)
- **Garbage Collection**: Removes orphaned chunks (runs every 6 hours)
- **Storage Node Health Check**: Monitors node availability and disk space (runs every 30 minutes)

See [CELERY_INTEGRATION.md](CELERY_INTEGRATION.md) for detailed documentation on:
- How Celery tasks work
- Manual task execution
- Admin API endpoints for monitoring
- Configuration and deployment
## Accessing the Application

- Backend API: http://localhost:8000/api
- Admin Interface: http://localhost:8000/admin
- Simple File API: http://localhost:8000/api/files/ (basic CRUD)
- Distributed Storage API: http://localhost:8000/api/files/ (advanced chunked storage)

## API Documentation

### Distributed Storage API (Primary)

#### Upload File (Chunked with Deduplication)
- **POST** `/api/files/upload/`
- **Authentication**: Required
- **Rate Limit**: 10 requests per 60 seconds
- **Request**: Multipart form data with 'file' field
- **Max File Size**: 100MB
- **Response**: File metadata including ID, filename, size, checksum, and timestamps
- **Features**:
  - Automatic file chunking (256KB chunks)
  - Content-based deduplication
  - Multi-node replication (3x)
  - Quota enforcement

#### List Files (With Filtering)
- **GET** `/api/files/`
- **Authentication**: Required
- **Query Parameters**:
  - `filename`: Search by filename (case-insensitive partial match)
  - `min_size`: Minimum file size in bytes
  - `max_size`: Maximum file size in bytes
  - `modified_after`: Filter files modified after date (ISO format)
  - `modified_before`: Filter files modified before date (ISO format)
  - `ordering`: Sort by `filename`, `size_bytes`, `created_at`, or `modified_at` (prefix with `-` for descending)
- **Response**: List of files with metadata

#### Delete File
- **DELETE** `/api/files/<file_id>/delete/`
- **Authentication**: Required
- **Response**: Success confirmation
- **Features**:
  - Automatic chunk cleanup
  - Reference counting
  - Quota adjustment
  - Physical deletion of unreferenced chunks

### Simple File API (Legacy)

#### List Files (Basic)
- **GET** `/api/files/`
- Returns list of uploaded files
- Response includes file metadata

#### Upload File (Basic)
- **POST** `/api/files/`
- Upload file via multipart form data
- Returns file metadata including ID

#### Get File Details
- **GET** `/api/files/<file_id>/`
- Retrieve specific file details
- Returns complete file metadata

#### Delete File (Basic)
- **DELETE** `/api/files/<file_id>/`
- Remove file from system
- Returns 204 No Content on success

## Project Structure

```
file-vault/
├── backend/                    # Django backend
│   ├── core/                  # Project settings
│   │   ├── settings.py        # Main configuration
│   │   └── urls.py            # URL routing
│   ├── files/                 # Simple file management app
│   │   ├── models.py          # Basic file model
│   │   ├── views.py           # CRUD API views
│   │   ├── urls.py            # URL routing
│   │   └── serializers.py     # Data serialization
│   ├── data/                  # Distributed storage app
│   │   ├── models.py          # Chunk, quota, and file models
│   │   ├── views.py           # Advanced API views
│   │   ├── serializers.py     # Data serialization
│   │   ├── filters.py         # Query filtering
│   │   ├── urls.py            # URL routing
│   │   └── services/          # Business logic
│   │       ├── chunking.py    # File chunking & hashing
│   │       ├── object_store.py # Storage node management
│   │       ├── upload_service.py # Upload handling
│   │       ├── delete_service.py # Deletion with cleanup
│   │       ├── quota.py       # Quota management
│   │       └── rate_limiter.py # Rate limiting
│   ├── object_store_node{1,2,3}/ # Storage nodes
│   ├── data/                  # SQLite database
│   ├── logs/                  # Application logs
│   ├── media/                 # Simple file storage
│   └── requirements.txt       # Python dependencies
├── docker-compose.yml         # Docker composition
└── .gitignore                 # Git ignore rules
```

## Development Features

- Comprehensive logging at all endpoints
- Structured logging with context (user_id, file_id, etc.)
- Hot reloading for backend development
- SQLite for easy development
- Redis-based rate limiting (gracefully degrades if unavailable)
- Detailed error responses with proper HTTP status codes
- Query filtering and sorting on file listings

## Troubleshooting

1. **Port Conflicts**
   ```bash
   # If port 8000 is in use, modify docker-compose.yml or use:
   python manage.py runserver 8001
   ```

2. **File Upload Issues**
   - Maximum file size: 100MB (configurable in serializers.py)
   - Check user quota status (default 5GB per user)
   - Verify storage nodes are accessible
   - Check logs in backend/logs/django.log

3. **Database Issues**
   ```bash
   # Reset database
   rm backend/data/db.sqlite3
   python manage.py migrate
   ```

4. **Redis Connection Issues**
   - Rate limiting will be disabled if Redis is unavailable
   - Check Redis is running: `redis-cli ping`
   - Start Redis: `redis-server` (Linux/Mac) or install Redis for Windows

5. **Storage Node Issues**
   - Verify all three storage node directories exist
   - Check permissions on object_store_node{1,2,3} directories
   - Review logs for chunk write/read failures

6. **Authentication Issues**
   - Create superuser: `python manage.py createsuperuser`
   - Distributed storage API requires authentication
   - Simple file API allows unauthenticated access

# Project Submission Instructions

## Preparing Your Submission

1. Before creating your submission zip file, ensure:
   - All features are implemented and working as expected
   - All tests are passing
   - The application runs successfully locally
   - Remove any unnecessary files or dependencies
   - Clean up any debug/console logs

2. Create the submission zip file:
   ```bash
   # Activate your backend virtual environment first
   cd backend
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Run the submission script from the project root
   cd ..
   python create_submission_zip.py
   ```

   The script will:
   - Create a zip file named `username_YYYYMMDD.zip` (e.g., `johndoe_20240224.zip`)
   - Respect .gitignore rules to exclude unnecessary files
   - Preserve file timestamps
   - Show you a list of included files and total size
   - Warn you if the zip is unusually large

3. Verify your submission zip file:
   - Extract the zip file to a new directory
   - Ensure all necessary files are included
   - Verify that no unnecessary files (like __pycache__, etc.) are included
   - Test the application from the extracted files to ensure everything works

## Video Documentation Requirement

**Video Guidance** - Record a screen share demonstrating:
- How you leveraged Gen AI to help build the features
- Your prompting techniques and strategies
- Any challenges you faced and how you overcame them
- Your thought process in using AI effectively

**IMPORTANT**: Please do not provide a demo of the application functionality. Focus only on your Gen AI usage and approach.

## Submission Process

1. Submit your project through this Google Form:
   [Project Submission Form](https://forms.gle/nr6DZAX3nv6r7bru9)

2. The form will require:
   - Your project zip file (named `username_YYYYMMDD.zip`)
   - Your video documentation
   - Any additional notes or comments about your implementation

Make sure to test the zip file and video before submitting to ensure they are complete and working as expected.

