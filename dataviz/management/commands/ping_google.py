from urllib.parse import quote

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
import requests


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        site_url = str(getattr(settings, "SITE_URL", "")).strip().rstrip("/")
        if not site_url:
            raise CommandError("SITE_URL is not configured. Set SITE_URL in environment.")

        sitemap_url = f"{site_url}/sitemap.xml"
        ping_url = f"https://www.google.com/ping?sitemap={quote(sitemap_url, safe=':/')}"

        response = requests.get(ping_url, timeout=15)
        response.raise_for_status()
        self.stdout.write(self.style.SUCCESS(f"Sitemap pinged successfully: {sitemap_url}"))
