#!/usr/bin/env python3
"""
Fix model field references in test files.

FileChunk objects (from stored_file.chunks) don't have ref_count directly.
They have a .chunk FK to ObjectChunk, which has ref_count.

Pattern to fix:
- chunk.ref_count -> chunk.chunk.ref_count
  (when chunk is a FileChunk from stored_file.chunks)
"""

import re
from pathlib import Path

test_dir = Path(__file__).parent
test_files = [
    'test_delete.py',
    'test_gc.py', 
    'test_file_chunks.py',
    'test_celery_integration.py'
]

def fix_ref_count_access(content):
    """Fix chunk.ref_count to chunk.chunk.ref_count"""
    # Pattern: chunk variable accessing ref_count directly
    # But need to preserve chunk.chunk.ref_count if already correct
    
    # First, protect already-correct patterns
    content = content.replace('chunk.chunk.ref_count', '<<<CORRECT_REF_COUNT>>>')
    
    # Fix incorrect patterns
    content = re.sub(r'\bchunk\.ref_count\b', 'chunk.chunk.ref_count', content)
    content = re.sub(r'\bchunk(\d+)\.ref_count\b', r'chunk\1.chunk.ref_count', content)
    content = re.sub(r'\bremaining_chunk\.ref_count\b', 'remaining_chunk.chunk.ref_count', content)
    
    # Restore protected patterns
    content = content.replace('<<<CORRECT_REF_COUNT>>>', 'chunk.chunk.ref_count')
    
    return content

def main():
    for filename in test_files:
        filepath = test_dir / filename
        if not filepath.exists():
            print(f"Skipping {filename} - file not found")
            continue
            
        print(f"Processing {filename}...", end=' ')
        
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        fixed_content = fix_ref_count_access(original_content)
        
        if fixed_content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            print("✓ Updated")
        else:
            print("No changes needed")

if __name__ == '__main__':
    main()
