from django.contrib.auth.signals import user_logged_in
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from blog.models import Blog

from .models import NewsletterSubscriber, StoredDataset
from .newsletter_service import send_newsletter_notification


def _full_url(path: str) -> str:
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not base:
        return path
    return f"{base}{path}"


@receiver(post_save, sender=Blog)
def notify_subscribers_for_new_blog(sender, instance: Blog, created: bool, **kwargs):
    if not created:
        return

    blog_path = reverse("dataviz:blog_dynamic", kwargs={"slug": instance.slug})
    blog_url = _full_url(blog_path)
    subject = f"New blog post: {instance.title}"
    body = (
        f"A new blog post is now available on DataViz Pro.\n\n"
        f"Title: {instance.title}\n"
        f"Read now: {blog_url}\n"
    )
    send_newsletter_notification(subject=subject, body=body)


@receiver(post_save, sender=StoredDataset)
def notify_subscribers_for_new_dataset(sender, instance: StoredDataset, created: bool, **kwargs):
    if not created:
        return

    datasets_path = reverse("dataviz:datasets")
    datasets_url = _full_url(datasets_path)
    subject = f"New dataset added: {instance.title}"
    body = (
        f"A new dataset has been added to the DataViz Pro store.\n\n"
        f"Dataset: {instance.title}\n"
        f"Explore datasets: {datasets_url}\n"
    )
    send_newsletter_notification(subject=subject, body=body)


@receiver(user_logged_in)
def auto_subscribe_user_on_login(sender, request, user, **kwargs):
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return

    subscriber, created = NewsletterSubscriber.objects.get_or_create(
        email=email,
        defaults={"is_active": True},
    )

    if not created and not subscriber.is_active:
        subscriber.is_active = True
        subscriber.save(update_fields=["is_active", "updated_at"])
