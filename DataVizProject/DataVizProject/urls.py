from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import TemplateView
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    # Main site
    path("", include("dataviz.urls")),

    # Blog app (namespace works correctly)
    path("blog/", include(("blog.urls", "blog"), namespace="blog")),

    # Robots
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
    ),
]

# Serve media in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
