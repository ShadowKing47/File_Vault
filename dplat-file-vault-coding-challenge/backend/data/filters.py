from django_filters import rest_framework as filters
from data.models import StoredFile


class FileFilter(filters.FilterSet):
    """Filter for stored files with various query options"""
    filename = filters.CharFilter(field_name="filename", lookup_expr="icontains")
    min_size = filters.NumberFilter(field_name="size_bytes", lookup_expr="gte")
    max_size = filters.NumberFilter(field_name="size_bytes", lookup_expr="lte")
    modified_after = filters.DateTimeFilter(field_name="modified_at", lookup_expr="gte")
    modified_before = filters.DateTimeFilter(field_name="modified_at", lookup_expr="lte")

    ordering = filters.OrderingFilter(
        fields=(
            ("filename", "filename"),
            ("size_bytes", "size_bytes"),
            ("created_at", "created_at"),
            ("modified_at", "modified_at"),
        ),
        field_labels={
            "filename": "File Name",
            "size_bytes": "File Size",
            "created_at": "Created Date",
            "modified_at": "Modified Date",
        }
    )

    class Meta:
        model = StoredFile
        fields = ["filename", "min_size", "max_size", "modified_after", "modified_before"]
