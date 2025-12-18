from django.shortcuts import render
from django.http import Http404
from .data import SEO_PAGES

def programmatic_seo_page(request, slug):
    page = next((p for p in SEO_PAGES if p["slug"] == slug), None)
    if not page:
        raise Http404()

    return render(request, "dataviz/seo/programmatic.html", {
        "page": page
    })
