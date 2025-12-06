from rest_framework import serializers
from .models import File


class FileSerializer(serializers.ModelSerializer):
    """Serializer for basic file model with validation"""
    
    class Meta:
        model = File
        fields = ['id', 'file', 'original_filename', 'file_type', 'size', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']
    
    def validate_file(self, value):
        """Validate file size"""
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size cannot exceed {max_size / (1024 * 1024)}MB"
            )
        return value
    
    def validate_size(self, value):
        """Validate size field"""
        if value < 0:
            raise serializers.ValidationError("File size cannot be negative")
        return value 