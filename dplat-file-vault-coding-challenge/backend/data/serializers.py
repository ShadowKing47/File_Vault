from rest_framework import serializers
from django.contrib.auth.models import User
from data.models import StoredFile, UserQuota


class UserQuotaSerializer(serializers.ModelSerializer):
    """Serializer for user quota information"""
    user = serializers.StringRelatedField(read_only=True)
    used_mb = serializers.SerializerMethodField()
    limit_mb = serializers.SerializerMethodField()

    class Meta:
        model = UserQuota
        fields = [
            "id",
            "user",
            "storage_limit_bytes",
            "storage_used_bytes",
            "used_mb",
            "limit_mb",
        ]
        read_only_fields = ["id", "user", "storage_used_bytes"]

    def get_used_mb(self, obj):
        """Convert used bytes to MB"""
        return round(obj.storage_used_bytes / (1024 * 1024), 2)

    def get_limit_mb(self, obj):
        """Convert limit bytes to MB"""
        return round(obj.storage_limit_bytes / (1024 * 1024), 2)


class FileUploadSerializer(serializers.Serializer):
    """Serializer for file upload validation"""
    file = serializers.FileField(required=True, allow_empty_file=True)

    def validate_file(self, value):
        """Validate file size"""
        if value.size > 100 * 1024 * 1024:  # 100MB limit
            raise serializers.ValidationError("File size cannot exceed 100MB")
        return value


class StoredFileSerializer(serializers.ModelSerializer):
    """Detailed serializer for stored files"""
    owner = serializers.StringRelatedField(read_only=True)
    size_mb = serializers.SerializerMethodField()
    file_id = serializers.IntegerField(source='id', read_only=True)

    class Meta:
        model = StoredFile
        fields = [
            "file_id",
            "id",
            "owner",
            "filename",
            "size_bytes",
            "size_mb",
            "created_at",
            "modified_at",
            "file_checksum",
        ]
        read_only_fields = ["id", "owner", "created_at", "modified_at", "file_checksum"]

    def get_size_mb(self, obj):
        """Convert size to MB for readability"""
        return round(obj.size_bytes / (1024 * 1024), 2)


class StoredFileListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for file listings"""
    size_mb = serializers.SerializerMethodField()

    class Meta:
        model = StoredFile
        fields = ["id", "filename", "size_bytes", "size_mb", "created_at", "modified_at"]
        read_only_fields = ["id", "created_at", "modified_at"]

    def get_size_mb(self, obj):
        """Convert size to MB for readability"""
        return round(obj.size_bytes / (1024 * 1024), 2)

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "password_confirm"]

    def validate(self, data):
        if data.get('password') != data.get('password_confirm'):
            raise serializers.ValidationError({"password": "Passwords do not match"})
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"]
        )
        return user

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]
        read_only_fields = ["id", "username"]

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)
    new_password_confirm = serializers.CharField(required=True)

    def validate(self, data):
        if data.get('new_password') != data.get('new_password_confirm'):
            raise serializers.ValidationError({"new_password": "Passwords do not match"})
        return data
