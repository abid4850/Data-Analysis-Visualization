from django.core.management.base import BaseCommand
import requests

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        sitemap_url = "https://yourdomain.com/sitemap.xml"
        ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
        requests.get(ping_url)
        self.stdout.write("Sitemap pinged successfully")
