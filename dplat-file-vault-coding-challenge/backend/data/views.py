import logging

from django.contrib.auth import authenticate
from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.generics import ListAPIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from data.models import StoredFile
from data.serializers import (
    FileUploadSerializer,
    StoredFileSerializer,
    StoredFileListSerializer,
    UserQuotaSerializer,
    UserRegistrationSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer
)
from data.services.upload_service import handle_file_upload
from data.services.delete_service import delete_file
from data.services.download_service import get_file_for_download, stream_file_chunks
from data.services.quota import QuotaExceededError, get_quota_status
from data.services.rate_limiter import sliding_window
from data.filters import FileFilter

logger = logging.getLogger(__name__)


def error_response(message, status_code=status.HTTP_400_BAD_REQUEST, **extra_data):
    """Unified error response format"""
    response_data = {"error": message}
    response_data.update(extra_data)
    return Response(response_data, status=status_code)


class FileUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    @sliding_window(limit=10, window_sec=60)
    def post(self, request, *args, **kwargs):
        logger.info("File upload request started", extra={"user_id": request.user.id})

        serializer = FileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(
                "File upload validation failed",
                extra={
                    "user_id": request.user.id,
                    "errors": serializer.errors,
                },
            )
            # Let DRF handle the error format
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        upload_file = serializer.validated_data["file"]
        logger.info(
            "File upload validated",
            extra={
                "user_id": request.user.id,
                "file_name": upload_file.name,
                "size_bytes": getattr(upload_file, "size", None),
            },
        )

        try:
            stored_file = handle_file_upload(request.user, upload_file)
        except QuotaExceededError as e:
            quota = get_quota_status(request.user)
            logger.warning(
                "Quota exceeded during file upload",
                extra={
                    "user_id": request.user.id,
                    "file_name": upload_file.name,
                    "limit_bytes": quota.limit,
                    "used_bytes": quota.used,
                    "remaining_bytes": quota.remaining,
                    "error": str(e),
                },
            )
            return Response(
                {
                    "detail": str(e),
                    "limit_bytes": quota.limit,
                    "used_bytes": quota.used,
                    "remaining_bytes": quota.remaining,
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        except Exception as e:
            logger.exception(
                "Unexpected error during file upload",
                extra={
                    "user_id": request.user.id,
                    "file_name": getattr(upload_file, "name", None),
                },
            )
            return error_response(
                "Internal server error during file upload",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        out = StoredFileSerializer(stored_file)
        logger.info(
            "File upload completed successfully",
            extra={
                "user_id": request.user.id,
                "stored_file_id": stored_file.id,
                "file_name": stored_file.filename,
                "size_bytes": stored_file.size_bytes,
            },
        )
        return Response(out.data, status=status.HTTP_201_CREATED)


class FileDownloadView(APIView):
    """API view for file download with streaming"""
    permission_classes = [permissions.IsAuthenticated]

    @sliding_window(limit=20, window_sec=60)
    def get(self, request, file_id, *args, **kwargs):
        """Stream file download"""
        logger.info(
            "File download request started",
            extra={"user_id": request.user.id, "file_id": file_id}
        )

        try:
            stored_file = get_file_for_download(request.user, file_id)
            
            # Create streaming response
            response = StreamingHttpResponse(
                stream_file_chunks(stored_file),
                content_type='application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{stored_file.filename}"'
            response['Content-Length'] = stored_file.size_bytes
            
            logger.info(
                "File download started",
                extra={
                    "user_id": request.user.id,
                    "file_id": file_id,
                    "file_name": stored_file.filename,
                    "size_bytes": stored_file.size_bytes
                }
            )
            
            return response
            
        except FileNotFoundError as e:
            logger.warning(
                "File not found during download",
                extra={"user_id": request.user.id, "file_id": file_id, "error": str(e)}
            )
            return error_response("File not found or access denied", status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception(
                "Unexpected error during file download",
                extra={"user_id": request.user.id, "file_id": file_id}
            )
            return error_response(
                "Internal server error during file download",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FileDeleteView(APIView):
    """API view for file deletion"""
    permission_classes = [permissions.IsAuthenticated]

    @sliding_window(limit=10, window_sec=60)
    def delete(self, request, file_id, *args, **kwargs):
        """Delete a file and its associated chunks"""
        logger.info(
            "File deletion request started",
            extra={"user_id": request.user.id, "file_id": file_id}
        )

        try:
            delete_file(request.user, file_id)
            logger.info(
                "File deleted successfully",
                extra={"user_id": request.user.id, "file_id": file_id}
            )
            return Response({"detail": "File deleted successfully"}, status=status.HTTP_200_OK)
        except FileNotFoundError as e:
            logger.warning(
                "File not found during deletion",
                extra={"user_id": request.user.id, "file_id": file_id, "error": str(e)}
            )
            return error_response("File not found or access denied", status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception(
                "Unexpected error during file deletion",
                extra={"user_id": request.user.id, "file_id": file_id}
            )
            return error_response(
                "Internal server error during file deletion",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FileListView(ListAPIView):
    """API view for listing user files with filtering and sorting"""
    """API view for listing user files with filtering and sorting"""
    permission_classes = [permissions.IsAuthenticated]

    serializer_class = StoredFileListSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = FileFilter

    ordering_fields = ["filename", "size_bytes", "created_at", "modified_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Return files owned by the current user"""
        logger.info(
            "File list request",
            extra={"user_id": self.request.user.id}
        )
        return StoredFile.objects.filter(owner=self.request.user)

    def handle_exception(self, exc):
        """Log exceptions during file listing"""
        logger.exception(
            "Error during file listing",
            extra={"user_id": self.request.user.id if self.request.user.is_authenticated else None}
        )
        return super().handle_exception(exc)

class UserQuotaView(APIView):
    """API view for checking user quota status"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get current user's quota information"""
        logger.info("User quota request", extra={"user_id": request.user.id})
        
        try:
            quota_status = get_quota_status(request.user)
            quota_obj = request.user.quota
            serializer = UserQuotaSerializer(quota_obj)
            data = serializer.data
            data["remaining_bytes"] = quota_status.remaining
            
            logger.info(
                "User quota retrieved",
                extra={
                    "user_id": request.user.id,
                    "used_bytes": quota_obj.storage_used_bytes,
                    "limit_bytes": quota_obj.storage_limit_bytes,
                }
            )
            return Response(data)
        except Exception as e:
            logger.exception(
                "Error retrieving user quota",
                extra={"user_id": request.user.id}
            )
            return error_response(
                "Internal server error",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserRegistrationView(APIView):
    """API view for user registration"""
    permission_classes = [permissions.AllowAny]

    @sliding_window(limit=5, window_sec=300)
    def post(self, request):
        """Register a new user"""
        logger.info("User registration request", extra={"username": request.data.get("username")})
        
        serializer = UserRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(
                "User registration validation failed",
                extra={
                    "username": request.data.get("username"),
                    "errors": serializer.errors
                }
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = serializer.save()
            logger.info(
                "User registered successfully",
                extra={"user_id": user.id, "username": user.username}
            )
            return Response(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "message": "User registered successfully"
                },
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.exception(
                "Error during user registration",
                extra={"username": request.data.get("username")}
            )
            return error_response(
                "Internal server error during registration",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserProfileView(APIView):
    """API view for user profile management"""
    permission_classes = [permissions.IsAuthenticated]

    @sliding_window(limit=20, window_sec=60)
    def get(self, request):
        """Get current user profile"""
        logger.info("User profile request", extra={"user_id": request.user.id})
        
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @sliding_window(limit=10, window_sec=60)
    def put(self, request):
        """Update current user profile"""
        logger.info("User profile update request", extra={"user_id": request.user.id})
        
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            logger.warning(
                "User profile update validation failed",
                extra={"user_id": request.user.id, "errors": serializer.errors}
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            serializer.save()
            logger.info(
                "User profile updated successfully",
                extra={"user_id": request.user.id}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(
                "Error during user profile update",
                extra={"user_id": request.user.id}
            )
            return error_response(
                "Internal server error during profile update",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChangePasswordView(APIView):
    """API view for password change"""
    permission_classes = [permissions.IsAuthenticated]

    @sliding_window(limit=5, window_sec=300)
    def post(self, request):
        """Change user password"""
        logger.info("Password change request", extra={"user_id": request.user.id})
        
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(
                "Password change validation failed",
                extra={"user_id": request.user.id, "errors": serializer.errors}
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        old_password = serializer.validated_data["old_password"]
        new_password = serializer.validated_data["new_password"]
        
        if not request.user.check_password(old_password):
            logger.warning(
                "Password change failed: incorrect old password",
                extra={"user_id": request.user.id}
            )
            return error_response("Incorrect old password", status.HTTP_400_BAD_REQUEST)
        
        try:
            request.user.set_password(new_password)
            request.user.save()
            logger.info(
                "Password changed successfully",
                extra={"user_id": request.user.id}
            )
            return Response(
                {"message": "Password changed successfully"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.exception(
                "Error during password change",
                extra={"user_id": request.user.id}
            )
            return error_response(
                "Internal server error during password change",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
