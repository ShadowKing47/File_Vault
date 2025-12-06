#!/bin/sh

# Ensure required directories exist with proper permissions
mkdir -p /app/data
mkdir -p /app/logs
mkdir -p /app/media
mkdir -p /app/staticfiles
mkdir -p /app/object_store_node1
mkdir -p /app/object_store_node2
mkdir -p /app/object_store_node3

chmod -R 777 /app/data /app/logs /app/media /app/staticfiles
chmod -R 777 /app/object_store_node1 /app/object_store_node2 /app/object_store_node3

# Run migrations
echo "Running migrations..."
python manage.py makemigrations
python manage.py migrate

# Create superuser if it doesn't exist (optional, commented out by default)
# echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'admin@example.com', 'admin')" | python manage.py shell

# Start server
echo "Starting server..."
gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 core.wsgi:application 