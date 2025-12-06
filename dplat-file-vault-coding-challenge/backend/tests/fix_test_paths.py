"""
Script to update test file paths and model references.
"""
import os
import re

test_dir = r"c:\Users\91995\OneDrive\Desktop\Backend-file-vault-coding-challenge\dplat-file-vault-coding-challenge\backend\tests"

# Files to update
test_files = [
    'test_upload.py',
    'test_dedup.py',
    'test_quota.py',
    'test_download.py',
    'test_delete.py',
    'test_gc.py',
    'test_search.py',
    'test_stress.py',
    'test_file_chunks.py',
    'test_celery_integration.py'
]

# Replacements to make
replacements = [
    (r'/api/data/upload/', '/api/files/upload/'),
    (r'/api/data/delete/(\d+)/', r'/api/files/\1/delete/'),
    (r'/api/data/download/(\d+)/', r'/api/files/\1/download/'),
    (r'/api/data/quota/', '/api/quota/'),
    (r'/api/data/auth/', '/api/auth/'),
]

# Model field fixes - only for references to FileChunk relationships
# chunks[0].checksum should be chunks[0].chunk.checksum
# But chunk.checksum (ObjectChunk) stays as is

for filename in test_files:
    filepath = os.path.join(test_dir, filename)
    
    if not os.path.exists(filepath):
        print(f"Skipping {filename} - not found")
        continue
    
    print(f"Processing {filename}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Apply replacements
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    # Fix chunk references - only when accessing through StoredFile.chunks relationship
    # Pattern: variable.chunks -> FileChunk objects, so need .chunk.checksum
    # But ObjectChunk.objects -> ObjectChunk, so keep .checksum
    
    # Fix chunks[idx].checksum to chunks[idx].chunk.checksum
    content = re.sub(r'chunks\[(\d+)\]\.checksum', r'chunks[\1].chunk.checksum', content)
    
    # Fix chunk1.checksum where chunk1 comes from stored_file.chunks
    # This is tricky - need context. Let's be conservative and fix obvious patterns
    
    # Patterns like: chunk = stored_file.chunks.first(); chunk.checksum
    # After chunks.first() or chunks.get() or chunks.all()[idx], we have FileChunk
    content = re.sub(r'(stored_file\.chunks\.(?:first|last|get)\(\))\s*\n\s*(\w+)\s*=\s*\1.*?\n.*?\2\.checksum', 
                     r'\1\n\2 = \1\n...\2.chunk.checksum', content)
    
    # Simple pattern: chunk = stored_file.chunks.first() followed by chunk.checksum
    # We'll handle this with a more targeted approach in the file itself
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Updated {filename}")
    else:
        print(f"  No changes needed for {filename}")

print("Done!")
