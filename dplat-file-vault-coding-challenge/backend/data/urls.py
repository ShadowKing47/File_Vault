from django.urls import path
from data.views import (
    FileUploadView,
    FileDownloadView,
    FileDeleteView,
    FileListView,
    UserQuotaView,
    UserRegistrationView,
    UserProfileView,
    ChangePasswordView
)
from data.admin_views import (
    StorageHealthView,
    ReplicationStatusView,
    GarbageCollectionView,
    ChunkIntegrityView
)


urlpatterns = [
    path("files/upload/", FileUploadView.as_view(), name="file-upload"),
    path("files/<int:file_id>/download/", FileDownloadView.as_view(), name="file-download"),
    path("files/<int:file_id>/delete/", FileDeleteView.as_view(), name="file-delete"),
    path("files/", FileListView.as_view(), name="file-list"),
    path("quota/", UserQuotaView.as_view(), name="user-quota"),
    
    # User management endpoints
    path("auth/register/", UserRegistrationView.as_view(), name="user-register"),
    path("auth/profile/", UserProfileView.as_view(), name="user-profile"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="change-password"),
    
    # Admin endpoints for storage monitoring and maintenance
    path("admin/storage/health/", StorageHealthView.as_view(), name="storage-health"),
    path("admin/storage/replication/", ReplicationStatusView.as_view(), name="replication-status"),
    path("admin/storage/garbage-collection/", GarbageCollectionView.as_view(), name="garbage-collection"),
    path("admin/storage/chunk-integrity/", ChunkIntegrityView.as_view(), name="chunk-integrity"),
]