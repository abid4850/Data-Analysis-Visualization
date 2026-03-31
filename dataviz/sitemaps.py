from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import Blog
from dataviz.seo.data import SEO_PAGES

class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return [
            'home',
            'about',
            'datasets',
            'blog',
            'online_data_visualization',
            'python_data_visualization',
            'data_visualization_dashboard',
            'data_visualization_examples',
            'data_visualization_cheat_sheet',
            'python_visualization_examples',
            'visualize_sales_data',
            'visualize_financial_data',
            'visualize_healthcare_data',
            'compare_tableau',
            'compare_powerbi',
            'dataviz_vs_excel',
            'dataviz_vs_google_sheets',
            'dataviz_vs_plotly',
        ]

    def location(self, item):
        return reverse(f'dataviz:{item}')


class ProgrammaticSEOSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return SEO_PAGES

    def location(self, item):
        return reverse('dataviz:programmatic_seo', kwargs={'slug': item['slug']})


class BlogPostSitemap(Sitemap):
    priority = 0.7
    changefreq = "weekly"

    def items(self):
        return Blog.objects.order_by('-created_at')

    def location(self, item):
        return reverse('dataviz:blog_dynamic', kwargs={'slug': item.slug})

    def lastmod(self, item):
        return item.created_at
