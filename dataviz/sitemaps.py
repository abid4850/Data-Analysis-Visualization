from django.contrib.sitemaps import Sitemap
from dataviz.seo.data import SEO_PAGES

class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return [
            'home',
            'about',
            'data_analysis',
            'online_data_visualization',
            'python_data_visualization',
            'data_visualization_dashboard',
        ]

    def location(self, item):
        from django.urls import reverse
        return reverse(item)


class ProgrammaticSEOSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return SEO_PAGES
