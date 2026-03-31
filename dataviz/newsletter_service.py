from typing import Iterable

from django.conf import settings
from django.core.mail import EmailMessage

from .models import NewsletterSubscriber


def _chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def send_newsletter_notification(subject: str, body: str):
    recipients = list(
        NewsletterSubscriber.objects.filter(is_active=True)
        .values_list("email", flat=True)
        .order_by("email")
    )

    if not recipients:
        return

    sender = getattr(settings, "DEFAULT_FROM_EMAIL", None) or None

    for batch in _chunked(recipients, 100):
        message = EmailMessage(
            subject=subject,
            body=body,
            from_email=sender,
            to=[],
            bcc=batch,
        )
        message.send(fail_silently=True)
