from django.urls import path
from django.contrib.sitemaps.views import sitemap

from . import views
from dataviz.sitemaps import StaticViewSitemap, ProgrammaticSEOSitemap
from dataviz.seo.views import programmatic_seo_page

app_name = "dataviz"

# Sitemaps
sitemaps = {
    "static": StaticViewSitemap,
    "seo": ProgrammaticSEOSitemap,
}

urlpatterns = [

    # Home & Analysis
    path("", views.home, name="home"),
    path("analysis/", views.data_analysis, name="data_analysis"),

    # Core pages
    path("about/", views.about, name="about"),
    path("datasets/", views.datasets, name="datasets"),
    path("datasets/global-sales-2024/", views.global_sales_2024, name="global_sales_2024"),
    path("datasets/student-performance-data/", views.student_performance_data, name="student_performance_data"),

    # Tools
    path("csv-visualizer/", views.csv_visualizer, name="csv_visualizer"),
    path("dataset-summary/", views.dataset_summary, name="dataset_summary"),
    path("chart-generator/", views.chart_generator, name="chart_generator"),

    # SEO / Examples
    path("online-data-visualization/", views.online_data_visualization, name="online_data_visualization"),
    path("python-data-visualization/", views.python_data_visualization, name="python_data_visualization"),
    path("data-visualization-dashboard/", views.data_visualization_dashboard, name="data_visualization_dashboard"),
    path("data-visualization-examples/", views.data_visualization_examples, name="data_visualization_examples"),
    path("data-visualization-cheat-sheet/", views.data_visualization_cheat_sheet, name="data_visualization_cheat_sheet"),
    path("python-visualization-examples/", views.python_visualization_examples, name="python_visualization_examples"),

    # Use Cases
    path("visualize-sales-data/", views.visualize_sales_data, name="visualize_sales_data"),
    path("visualize-financial-data/", views.visualize_financial_data, name="visualize_financial_data"),
    path("visualize-healthcare-data/", views.visualize_healthcare_data, name="visualize_healthcare_data"),

    # Comparisons
    path("dataviz-vs-tableau/", views.compare_tableau, name="compare_tableau"),
    path("dataviz-vs-power-bi/", views.compare_powerbi, name="compare_powerbi"),
    path("dataviz-vs-excel/", views.dataviz_vs_excel, name="dataviz_vs_excel"),
    path("dataviz-vs-google-sheets/", views.dataviz_vs_google_sheets, name="dataviz_vs_google_sheets"),
    path("dataviz-vs-plotly/", views.dataviz_vs_plotly, name="dataviz_vs_plotly"),

    # Blog
    path("blog/", views.blog_index, name="blog"),
    path("blog/upload-data-and-visualize-online/", views.blog_upload_visualize, name="blog_upload_visualize"),
    path("blog/<slug:slug>/", views.blog_dynamic, name="blog_dynamic"),

    # Sitemap
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),

    # Programmatic SEO (must be last)
    path("<slug:slug>/", programmatic_seo_page, name="programmatic_seo"),
]
