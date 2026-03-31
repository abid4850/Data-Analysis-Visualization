from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class DatasetTag(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "tag"
            candidate = base_slug
            suffix = 1
            while DatasetTag.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                suffix += 1
                candidate = f"{base_slug}-{suffix}"
            self.slug = candidate
        super().save(*args, **kwargs)


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-subscribed_at"]

    def __str__(self) -> str:
        return self.email


class StoredDataset(models.Model):
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    tags = models.ManyToManyField(DatasetTag, blank=True, related_name="datasets")
    dataset_file = models.FileField(upload_to="dataset_store/")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="stored_datasets",
        null=True,
        blank=True,
    )
    download_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def download_name(self) -> str:
        if self.original_filename:
            return self.original_filename
        return Path(self.dataset_file.name).name
