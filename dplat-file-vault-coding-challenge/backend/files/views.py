import logging
from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import File
from .serializers import FileSerializer
from data.services.rate_limiter import sliding_window

logger = logging.getLogger(__name__)


def error_response(message, status_code=status.HTTP_400_BAD_REQUEST, **extra_data):
    """Unified error response format"""
    response_data = {"error": message}
    response_data.update(extra_data)
    return Response(response_data, status=status_code)


class FileViewSet(viewsets.ModelViewSet):
    """Basic file management viewset with CRUD operations"""
    queryset = File.objects.all()
    serializer_class = FileSerializer

    @sliding_window(limit=10, window_sec=60)
    def create(self, request, *args, **kwargs):
        """Handle file upload with validation and logging"""
        logger.info("File upload request (simple API)", extra={"ip": request.META.get('REMOTE_ADDR')})
        
        file_obj = request.FILES.get('file')
        if not file_obj:
            logger.warning("File upload failed: no file provided")
            return error_response('No file provided', status.HTTP_400_BAD_REQUEST)
        
        data = {
            'file': file_obj,
            'original_filename': file_obj.name,
            'file_type': file_obj.content_type,
            'size': file_obj.size
        }
        
        logger.info(
            "Processing file upload",
            extra={
                "filename": file_obj.name,
                "size": file_obj.size,
                "content_type": file_obj.content_type
            }
        )
        
        try:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            
            logger.info(
                "File uploaded successfully",
                extra={"file_id": serializer.data['id'], "filename": file_obj.name}
            )
            
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            logger.exception("Error during file upload", extra={"filename": file_obj.name})
            return error_response(
                'Internal server error during file upload',
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @sliding_window(limit=10, window_sec=60)
    def destroy(self, request, *args, **kwargs):
        """Delete file with logging"""
        instance = self.get_object()
        logger.info("File deletion request", extra={"file_id": instance.id, "filename": instance.original_filename})
        
        try:
            self.perform_destroy(instance)
            logger.info("File deleted successfully", extra={"file_id": instance.id})
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.exception("Error during file deletion", extra={"file_id": instance.id})
            return error_response(
                'Internal server error during file deletion',
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def list(self, request, *args, **kwargs):
        """List files with logging"""
        logger.info("File list request")
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.exception("Error during file listing")
            return error_response(
                'Internal server error',
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        """Retrieve file details with logging"""
        logger.info("File retrieve request", extra={"file_id": kwargs.get('pk')})
        try:
            return super().retrieve(request, *args, **kwargs)
        except Exception as e:
            logger.exception("Error retrieving file", extra={"file_id": kwargs.get('pk')})
            return error_response(
                'Internal server error',
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
