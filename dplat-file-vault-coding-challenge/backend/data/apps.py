from django.apps import AppConfig


class DataConfig(AppConfig):
    """Configuration for the data app"""
    default_auto_field = "django.db.models.BigAutoField"
    name = "data"
    verbose_name = "Distributed Object Storage"
