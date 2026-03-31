from django.contrib import admin

from .models import DatasetTag, NewsletterSubscriber, StoredDataset


@admin.register(DatasetTag)
class DatasetTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(StoredDataset)
class StoredDatasetAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "uploaded_by",
        "download_count",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "created_at", "tags")
    search_fields = ("title", "description", "original_filename")
    readonly_fields = ("download_count", "created_at", "updated_at")
    filter_horizontal = ("tags",)


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "subscribed_at", "updated_at")
    list_filter = ("is_active", "subscribed_at")
    search_fields = ("email",)
