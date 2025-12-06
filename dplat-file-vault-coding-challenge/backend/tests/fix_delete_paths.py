#!/usr/bin/env python3
"""Fix remaining delete endpoint paths"""
import re

with open('test_delete.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix f-string delete paths: f'/api/data/delete/{var}/' -> f'/api/files/{var}/delete/'
content = re.sub(r"f'/api/data/delete/\{(\w+)\}/'", r"f'/api/files/{\1}/delete/'", content)

# Fix static delete paths: /api/data/delete/99999/ -> /api/files/99999/delete/
content = re.sub(r"'/api/data/delete/(\d+)/'", r"'/api/files/\1/delete/'", content)

with open('test_delete.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed test_delete.py delete endpoint paths")
