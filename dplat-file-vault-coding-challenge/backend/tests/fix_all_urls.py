#!/usr/bin/env python3
"""
Comprehensive fix for all test file URL paths.
"""
import re
from pathlib import Path

test_dir = Path(__file__).parent

# All test files
test_files = [
    'test_auth.py',
    'test_quota.py',
    'test_download.py',
    'test_gc.py',
    'test_rate_limit.py',
    'test_storage_nodes.py',
    'test_user_profile.py',
    'test_celery_integration.py',
    'test_stress.py',
]

def fix_urls(content):
    """Fix all /api/data/* URLs to correct paths"""
    # Auth endpoints: /api/data/auth/* -> /api/auth/*
    content = re.sub(r"'/api/data/auth/", "'/api/auth/", content)
    
    # Quota endpoints: /api/data/quota/* -> /api/quota/*
    content = re.sub(r"'/api/data/quota/", "'/api/quota/", content)
    
    # Upload endpoint: /api/data/upload/ -> /api/files/upload/
    content = re.sub(r"'/api/data/upload/", "'/api/files/upload/", content)
    
    # Delete endpoint (f-strings): f'/api/data/delete/{var}/' -> f'/api/files/{var}/delete/'
    content = re.sub(r"f'/api/data/delete/\{([^}]+)\}/'", r"f'/api/files/{\1}/delete/'", content)
    
    # Delete endpoint (static): '/api/data/delete/123/' -> '/api/files/123/delete/'
    content = re.sub(r"'/api/data/delete/(\d+)/'", r"'/api/files/\1/delete/'", content)
    
    # Download endpoint (f-strings): f'/api/data/download/{var}/' -> f'/api/files/{var}/download/'
    content = re.sub(r"f'/api/data/download/\{([^}]+)\}/'", r"f'/api/files/{\1}/download/'", content)
    
    # Download endpoint (static): '/api/data/download/123/' -> '/api/files/123/download/'
    content = re.sub(r"'/api/data/download/(\d+)/'", r"'/api/files/\1/download/'", content)
    
    return content

def main():
    for filename in test_files:
        filepath = test_dir / filename
        if not filepath.exists():
            print(f"Skipping {filename} - not found")
            continue
        
        print(f"Processing {filename}...", end=' ')
        
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        fixed_content = fix_urls(original_content)
        
        if fixed_content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            print("✓ Updated")
        else:
            print("No changes needed")

    print("\nDone! All test files updated.")

if __name__ == '__main__':
    main()
