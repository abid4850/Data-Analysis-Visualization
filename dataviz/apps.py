from django.apps import AppConfig


class DatavizConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dataviz"

    def ready(self):
        from . import signals  # noqa: F401
