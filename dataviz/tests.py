import tempfile
import os
import re
from io import StringIO
from urllib.parse import quote
from unittest.mock import patch

import pandas as pd
from blog.models import Blog
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from dataviz import data_processor
from dataviz.models import DatasetTag, NewsletterSubscriber, StoredDataset


class DatavizCoreFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_media = tempfile.TemporaryDirectory()
        cls.override = override_settings(
            MEDIA_ROOT=cls.temp_media.name,
            MAX_UPLOAD_SIZE_MB=1,
            MAX_ANALYSIS_ROWS=1000,
            MAX_ANALYSIS_COLUMNS=20,
            ANALYSIS_TIMEOUT_SECONDS=15,
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            SITE_URL="http://testserver",
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        )
        cls.override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        cls.temp_media.cleanup()
        super().tearDownClass()

    def test_home_page_loads(self):
        response = self.client.get(reverse("dataviz:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DataViz Pro", status_code=200)

    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_analysis_page_loads_with_sample_dataset(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        _mock_plot,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({"feature_a": [1, 2, 3], "feature_b": [4, 5, 6]}),
            None,
        )

        response = self.client.get(reverse("dataviz:data_analysis"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Data Analysis & Visualization Dashboard")
        self.assertContains(response, "Interactive Plot Studio (2D, 3D, and Geographic)")
        self.assertContains(response, "Plot Family")
        self.assertContains(response, "2D Plot Type")
        self.assertContains(response, "3D Plot Type")
        self.assertContains(response, "Geographic Plot Type")
        self.assertContains(response, "Analyst Briefing")
        self.assertContains(response, "Data Quality Signals")
        self.assertContains(response, "Actionable Recommendations")
        self.assertContains(response, "Executive Auto-Insights")
        self.assertContains(response, "Automatic Anomaly Alerts")
        self.assertContains(response, "Suggested Best Chart Type")
        self.assertContains(response, "Export Stakeholder Brief (.txt)")
        self.assertContains(response, "Export Stakeholder Brief (.pdf)")
        self.assertContains(response, "Apply This Suggestion")
        self.assertContains(response, "Dashboard Command Center")
        self.assertContains(response, "Analyst View")
        self.assertContains(response, "Boardroom View")
        self.assertContains(response, "dashboardViewShell")
        self.assertContains(response, "Viewing: Analyst")
        self.assertContains(response, "dashboardViewStatusIcon")
        self.assertContains(response, "fa-chart-line")
        self.assertContains(response, "fa-chalkboard-user")
        self.assertContains(response, "dashboard-view-status-icon-transition")
        self.assertContains(response, "dashboard-view-status-text-transition")

    @patch("dataviz.views.data_processor.generate_advanced_plotly_plot", return_value=("<div>geo-3d-plot</div>", None))
    @patch("dataviz.views.data_processor.generate_interactive_plot")
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_advanced_plot_submission_uses_plotly_generator(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        mock_2d_plot,
        mock_advanced_plot,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "x_value": [1, 2, 3, 4],
                "y_value": [2, 4, 6, 8],
                "z_value": [3, 6, 9, 12],
                "latitude": [37.77, 34.05, 40.71, 47.61],
                "longitude": [-122.42, -118.24, -74.00, -122.33],
                "country": ["United States", "United States", "United States", "United States"],
                "segment": ["A", "B", "A", "C"],
            }),
            None,
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "plot_type_select": "3D Scatter",
                "x_col_select": "x_value",
                "y_col_select": "y_value",
                "z_col_select": "z_value",
                "size_col_select": "z_value",
                "plot_color_col_select": "segment",
                "geo_lat_col_select": "latitude",
                "geo_lon_col_select": "longitude",
                "geo_location_col_select": "country",
                "geo_scope_select": "world",
                "geo_map_style_select": "carto-positron",
                "geo_projection_select": "natural earth",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Geo Density")
        self.assertContains(response, "3D Surface")
        self.assertContains(response, "Geo Choropleth")
        self.assertContains(response, "Location Mode")
        self.assertContains(response, "Color Scale")
        self.assertContains(response, "geo-3d-plot")

        kwargs = mock_advanced_plot.call_args.kwargs
        self.assertEqual(kwargs["plot_type"], "3D Scatter")
        self.assertEqual(kwargs["x_col"], "x_value")
        self.assertEqual(kwargs["y_col"], "y_value")
        self.assertEqual(kwargs["z_col"], "z_value")
        self.assertEqual(kwargs["color_col"], "segment")
        self.assertEqual(kwargs["size_col"], "z_value")
        self.assertEqual(kwargs["geo_scope"], "world")
        self.assertEqual(kwargs["geo_map_style"], "carto-positron")
        self.assertEqual(kwargs["geo_projection"], "natural earth")
        self.assertEqual(kwargs["geo_location_mode"], "country names")
        self.assertEqual(kwargs["geo_choropleth_color_scale"], "Blues")
        mock_2d_plot.assert_not_called()

    @patch("dataviz.views.data_processor.generate_advanced_plotly_plot", return_value=("<div>family-based-plot</div>", None))
    @patch("dataviz.views.data_processor.generate_interactive_plot")
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_plot_family_specific_selectors_drive_plot_type(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        mock_2d_plot,
        mock_advanced_plot,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "x_value": [1, 2, 3],
                "y_value": [2, 3, 4],
                "z_value": [3, 4, 5],
                "segment": ["A", "B", "A"],
            }),
            None,
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "plot_family_select": "3d",
                "plot_type_3d_select": "3D Surface",
                "x_col_select": "x_value",
                "y_col_select": "y_value",
                "z_col_select": "z_value",
                "plot_color_col_select": "segment",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "family-based-plot")

        kwargs = mock_advanced_plot.call_args.kwargs
        self.assertEqual(kwargs["plot_type"], "3D Surface")
        mock_2d_plot.assert_not_called()

    @patch("dataviz.views.data_processor.generate_advanced_plotly_plot", return_value=("<div>geo-choropleth-plot</div>", None))
    @patch("dataviz.views.data_processor.generate_interactive_plot")
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_geo_choropleth_submission_uses_advanced_generator(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        mock_2d_plot,
        mock_advanced_plot,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "sales": [100, 140, 170, 130],
                "country": ["United States", "Canada", "Mexico", "United States"],
                "segment": ["A", "A", "B", "C"],
                "year": [2021, 2021, 2022, 2022],
            }),
            None,
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "plot_type_select": "Geo Choropleth",
                "size_col_select": "sales",
                "plot_color_col_select": "segment",
                "geo_location_col_select": "country",
                "geo_location_mode_select": "country names",
                "geo_choropleth_color_scale_select": "Plasma",
                "geo_year_col_select": "year",
                "geo_scope_select": "world",
                "geo_map_style_select": "carto-positron",
                "geo_projection_select": "natural earth",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "geo-choropleth-plot")

        kwargs = mock_advanced_plot.call_args.kwargs
        self.assertEqual(kwargs["plot_type"], "Geo Choropleth")
        self.assertEqual(kwargs["location_col"], "country")
        self.assertEqual(kwargs["size_col"], "sales")
        self.assertEqual(kwargs["animation_col"], "year")
        self.assertEqual(kwargs["geo_location_mode"], "country names")
        self.assertEqual(kwargs["geo_choropleth_color_scale"], "Plasma")
        mock_2d_plot.assert_not_called()

    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    def test_csv_upload_flow_succeeds(self, _mock_pairplot, _mock_heatmap, _mock_plot):
        upload = SimpleUploadedFile(
            "sample.csv",
            b"x,y\n1,2\n3,4\n",
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {"file_upload": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uploaded")
        self.assertContains(response, "sample.csv")

    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    def test_json_upload_flow_succeeds(self, _mock_pairplot, _mock_heatmap, _mock_plot):
        upload = SimpleUploadedFile(
            "sample.json",
            b"[{\"x\": 1, \"y\": 2}, {\"x\": 3, \"y\": 4}]",
            content_type="application/json",
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {"file_upload": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uploaded")
        self.assertContains(response, "sample.json")

    def test_rejects_invalid_upload_type(self):
        upload = SimpleUploadedFile(
            "payload.exe",
            b"MZ-malicious-content",
            content_type="application/octet-stream",
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {"file_upload": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unsupported file type")

    @patch("dataviz.views.data_processor.generate_dashboard_panels")
    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    def test_market_matrix_csv_upload_enables_numeric_dashboard(
        self,
        _mock_pairplot,
        _mock_heatmap,
        _mock_plot,
        mock_dashboard,
    ):
        mock_dashboard.return_value = [
            {"title": "Metric Chart", "html": "<div>metric-chart</div>", "note": "n1"},
        ]

        csv_payload = (
            "Price,Close,Close.1,Close.2,High,High.1,High.2\n"
            "Ticker,BYDDF,TM,TSLA,BYDDF,TM,TSLA\n"
            "Date,,,,,,\n"
            "2018-01-02,2.85,104.70,21.36,2.88,104.74,21.47\n"
            "2018-01-03,2.95,106.13,21.15,2.95,106.22,21.68\n"
        )
        upload = SimpleUploadedFile(
            "auto_company_comparison.csv",
            csv_payload.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {"file_upload": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "metric-chart")
        kwargs = mock_dashboard.call_args.kwargs
        self.assertIsNotNone(kwargs["metric_col"])
        self.assertTrue(str(kwargs["metric_col"]).startswith("Close_"))

    def test_rejects_file_over_size_limit(self):
        oversized = b"a" * (1024 * 1024 + 1)
        upload = SimpleUploadedFile("too_large.csv", oversized, content_type="text/csv")

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {"file_upload": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "File is too large")

    def test_health_endpoint_ok(self):
        response = self.client.get(reverse("dataviz:health_check"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["database"], "ok")

    def test_robots_txt_exposes_runtime_sitemap_url(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User-agent: *")
        self.assertContains(response, "Disallow: /analysis/")
        self.assertContains(response, f"Sitemap: http://testserver{reverse('dataviz:sitemap')}")

    def test_sitemap_includes_blog_posts_and_excludes_analysis(self):
        Blog.objects.create(
            title="SEO Sitemaps Matter",
            slug="seo-sitemaps-matter",
            content="Sitemap indexing guidance.",
        )

        response = self.client.get(reverse("dataviz:sitemap"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<loc>http://testserver/blog/seo-sitemaps-matter/</loc>")
        self.assertNotContains(response, "<loc>http://testserver/analysis/</loc>")

    def test_canonical_url_omits_query_parameters(self):
        response = self.client.get(reverse("dataviz:datasets"), {"q": "sales", "sort": "title_desc"})
        canonical = f'<link rel="canonical" href="http://testserver{reverse("dataviz:datasets")}">'
        noncanonical = (
            f'<link rel="canonical" '
            f'href="http://testserver{reverse("dataviz:datasets")}?q=sales&amp;sort=title_desc">'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, canonical, html=True)
        self.assertNotContains(response, noncanonical, html=True)

    def test_priority_programmatic_page_renders_enriched_sections(self):
        response = self.client.get(
            reverse("dataviz:programmatic_seo", kwargs={"slug": "visualize-sales-data-with-bar-charts"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Questions This Page Can Answer")
        self.assertContains(response, "Suggested KPI Pack")
        self.assertContains(response, "Recommended Dataset Columns")
        self.assertContains(response, "Frequently Asked Questions")
        self.assertContains(response, '"@type": "FAQPage"')
        self.assertContains(response, "Related Guides")

    def test_non_priority_programmatic_page_keeps_standard_layout(self):
        response = self.client.get(
            reverse("dataviz:programmatic_seo", kwargs={"slug": "visualize-education-data-with-pie-charts"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Common Use Cases")
        self.assertContains(response, "How to Visualize This Data")
        self.assertNotContains(response, "Business Questions This Page Can Answer")

    def test_dataset_store_download_requires_login(self):
        dataset = StoredDataset.objects.create(
            title="Store Dataset",
            description="Store file for auth check",
            dataset_file=SimpleUploadedFile("store_sample.csv", b"a,b\n1,2\n", content_type="text/csv"),
            original_filename="store_sample.csv",
        )

        response = self.client.get(reverse("dataviz:dataset_store_download", args=[dataset.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_dataset_store_download_increments_count_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username="store_user")
        dataset = StoredDataset.objects.create(
            title="Auth Dataset",
            description="Auth download",
            dataset_file=SimpleUploadedFile("auth_dataset.csv", b"a,b\n5,6\n", content_type="text/csv"),
            original_filename="auth_dataset.csv",
            uploaded_by=user,
        )

        self.client.force_login(user)
        response = self.client.get(reverse("dataviz:dataset_store_download", args=[dataset.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.get("Content-Disposition", ""))
        dataset.refresh_from_db()
        self.assertEqual(dataset.download_count, 1)

    def test_download_login_flow_accepts_email_credentials(self):
        user = get_user_model().objects.create_user(
            username="email_login_user",
            email="email-login@example.com",
            password="safe-pass-123",
        )
        dataset = StoredDataset.objects.create(
            title="Email Auth Dataset",
            description="Auth via email",
            dataset_file=SimpleUploadedFile("email_auth.csv", b"a,b\n5,6\n", content_type="text/csv"),
            original_filename="email_auth.csv",
            uploaded_by=user,
        )

        download_url = reverse("dataviz:dataset_store_download", args=[dataset.id])
        response = self.client.post(
            reverse("login"),
            {
                "username": "email-login@example.com",
                "password": "safe-pass-123",
                "next": download_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        datasets_url = reverse("dataviz:datasets")
        self.assertEqual(response["Location"], f"{datasets_url}?download={dataset.id}")

        landing_response = self.client.get(response["Location"])
        self.assertEqual(landing_response.status_code, 200)
        self.assertContains(landing_response, "Click below to download your selected dataset")
        self.assertContains(landing_response, download_url)

    def test_dataset_page_login_link_points_to_selected_download(self):
        dataset = StoredDataset.objects.create(
            title="Link Target Dataset",
            description="Dataset for login link target",
            dataset_file=SimpleUploadedFile("link_target.csv", b"a,b\n1,2\n", content_type="text/csv"),
            original_filename="link_target.csv",
        )

        response = self.client.get(reverse("dataviz:datasets"))
        self.assertEqual(response.status_code, 200)

        download_url = reverse("dataviz:dataset_store_download", args=[dataset.id])
        encoded_download_url = quote(download_url, safe='')
        page_html = response.content.decode("utf-8")
        self.assertRegex(
            page_html,
            re.compile(rf"/accounts/login/\?next=({re.escape(encoded_download_url)}|{re.escape(download_url)})"),
        )

    def test_login_page_shows_download_hint_for_dataset_target(self):
        dataset = StoredDataset.objects.create(
            title="Hint Dataset",
            description="Dataset for login hint",
            dataset_file=SimpleUploadedFile("hint_dataset.csv", b"a,b\n1,2\n", content_type="text/csv"),
            original_filename="hint_dataset.csv",
        )

        download_url = reverse("dataviz:dataset_store_download", args=[dataset.id])
        response = self.client.get(reverse("login"), {"next": download_url})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "After login, you will see a clear Download button for your selected dataset")

    def test_login_page_rejects_non_email_identifier(self):
        get_user_model().objects.create_user(
            username="username_only_user",
            email="username-only@example.com",
            password="safe-pass-123",
        )

        response = self.client.post(
            reverse("login"),
            {
                "username": "username_only_user",
                "password": "safe-pass-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address")

    def test_login_page_shows_forgot_password_link(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("password_reset"))

    @patch("django.contrib.auth.forms.PasswordResetForm.save")
    def test_password_reset_sends_email_for_registered_user(self, mock_form_save):
        user = get_user_model().objects.create_user(
            username="reset_user",
            email="reset-user@example.com",
            password="safe-pass-123",
        )

        response = self.client.post(reverse("password_reset"), {"email": user.email})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("password_reset_done"))
        mock_form_save.assert_called_once()

    @patch("dataviz.views.data_processor.load_dataset")
    def test_stakeholder_brief_export_downloads_text_file(self, mock_load_dataset):
        mock_load_dataset.return_value = (
            pd.DataFrame(
                {
                    "date": [
                        "2024-01-01",
                        "2024-01-02",
                        "2024-01-03",
                        "2024-01-04",
                        "2024-01-05",
                        "2024-01-06",
                        "2024-01-07",
                        "2024-01-08",
                        "2024-01-09",
                    ],
                    "sales": [100, 102, 98, 101, 99, 103, 300, 101, 100],
                    "profit": [20, 18, 19, 21, 20, 22, 50, 21, 20],
                    "region": ["North", "South", "North", "South", "North", "South", "North", "South", "North"],
                }
            ),
            None,
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_metric_select": "sales",
                "dashboard_date_select": "date",
                "export_narrative": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])

        body = response.content.decode("utf-8")
        self.assertIn("Stakeholder Brief - DataViz Pro", body)
        self.assertIn("Executive Auto-Insights", body)
        self.assertIn("Automatic Anomaly Alerts", body)
        self.assertIn("Recommended Chart Types", body)

    @patch("dataviz.views.data_processor.load_dataset")
    def test_stakeholder_brief_export_downloads_pdf_file(self, mock_load_dataset):
        mock_load_dataset.return_value = (
            pd.DataFrame(
                {
                    "date": [
                        "2024-01-01",
                        "2024-01-02",
                        "2024-01-03",
                        "2024-01-04",
                        "2024-01-05",
                        "2024-01-06",
                        "2024-01-07",
                        "2024-01-08",
                    ],
                    "sales": [100, 102, 98, 101, 99, 103, 300, 101],
                    "profit": [20, 18, 19, 21, 20, 22, 50, 21],
                    "region": ["North", "South", "North", "South", "North", "South", "North", "South"],
                }
            ),
            None,
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_metric_select": "sales",
                "dashboard_date_select": "date",
                "export_narrative": "1",
                "export_narrative_format": "pdf",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))

    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_apply_chart_suggestion_auto_selects_plot_config(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        mock_plot,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame(
                {
                    "sales": [100, 120, 140, 180],
                    "profit": [20, 25, 31, 44],
                    "lat": [37.77, 34.05, 40.71, 47.61],
                    "lon": [-122.42, -118.24, -74.00, -122.33],
                }
            ),
            None,
        )

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "apply_chart_suggestion": "1",
                "suggestion_plot_type": "Line",
                "plot_family_select": "2d",
                "plot_type_select": "Line",
                "plot_type_2d_select": "Line",
                "x_col_select": "sales",
                "y_col_select": "profit",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applied suggestion: Line")
        self.assertContains(response, "interactivePlotCard")
        self.assertContains(response, "const suggestionApplied = true")
        self.assertContains(response, "chart-focus-pulse")

        args = mock_plot.call_args.args
        self.assertEqual(args[1], "sales")
        self.assertEqual(args[2], "profit")
        self.assertEqual(args[3], "Line")

    @override_settings(
        PASSWORD_RESET_FROM_EMAIL="Security Team <security@dataviz.example>",
        PASSWORD_RESET_USE_HTTPS=True,
        PASSWORD_RESET_DOMAIN_OVERRIDE="dataviz.example.com",
    )
    @patch("django.contrib.auth.forms.PasswordResetForm.send_mail")
    def test_password_reset_uses_configured_sender_and_domain(self, mock_send_mail):
        user = get_user_model().objects.create_user(
            username="reset_user_configured",
            email="reset-configured@example.com",
            password="safe-pass-123",
        )

        response = self.client.post(reverse("password_reset"), {"email": user.email})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("password_reset_done"))
        mock_send_mail.assert_called_once()
        send_args = mock_send_mail.call_args.args
        context = send_args[2]
        self.assertEqual(send_args[3], "Security Team <security@dataviz.example>")
        self.assertEqual(send_args[4], "reset-configured@example.com")
        self.assertEqual(context["domain"], "dataviz.example.com")
        self.assertEqual(context["protocol"], "https")

    @override_settings(
        PASSWORD_RESET_FROM_EMAIL="Security Team <security@dataviz.example>",
        PASSWORD_RESET_USE_HTTPS=True,
        PASSWORD_RESET_DOMAIN_OVERRIDE="dataviz.example.com",
    )
    @patch("dataviz.management.commands.send_test_reset_email.PasswordResetForm.save")
    def test_send_test_reset_email_command_sends_reset_email(self, mock_form_save):
        user = get_user_model().objects.create_user(
            username="cmd_reset_user",
            email="cmd-reset@example.com",
            password="safe-pass-123",
        )
        output = StringIO()

        call_command(
            "send_test_reset_email",
            "--email",
            user.email,
            stdout=output,
        )

        self.assertIn("Password reset email sent", output.getvalue())
        mock_form_save.assert_called_once()
        save_kwargs = mock_form_save.call_args.kwargs
        self.assertTrue(save_kwargs["use_https"])
        self.assertEqual(save_kwargs["from_email"], "Security Team <security@dataviz.example>")
        self.assertEqual(save_kwargs["domain_override"], "dataviz.example.com")

    @override_settings(
        PASSWORD_RESET_FROM_EMAIL="Security Team <security@dataviz.example>",
        PASSWORD_RESET_USE_HTTPS=True,
        PASSWORD_RESET_DOMAIN_OVERRIDE="dataviz.example.com",
    )
    @patch("dataviz.management.commands.send_test_reset_email.PasswordResetForm.save")
    def test_send_test_reset_email_command_can_create_user(self, mock_form_save):
        output = StringIO()

        call_command(
            "send_test_reset_email",
            "--email",
            "created-reset@example.com",
            "--create-user",
            stdout=output,
        )

        created_user = get_user_model().objects.get(email="created-reset@example.com")
        self.assertTrue(created_user.has_usable_password())
        self.assertIn("Created active test user", output.getvalue())
        self.assertIn("Password reset email sent", output.getvalue())
        mock_form_save.assert_called_once()

    @override_settings(
        EMAIL_HOST="smtp.example.com",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="apikey",
        EMAIL_HOST_PASSWORD="secret",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        EMAIL_TIMEOUT=20,
    )
    @patch("dataviz.management.commands.test_smtp_connection.get_connection")
    def test_test_smtp_connection_command_success(self, mock_get_connection):
        mock_connection = mock_get_connection.return_value
        output = StringIO()

        call_command("test_smtp_connection", stdout=output)

        self.assertIn("SMTP connection successful", output.getvalue())
        mock_connection.open.assert_called_once()
        mock_connection.close.assert_called_once()

    @override_settings(
        EMAIL_HOST="smtp.example.com",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="apikey",
        EMAIL_HOST_PASSWORD="secret",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        EMAIL_TIMEOUT=20,
    )
    @patch("dataviz.management.commands.test_smtp_connection.get_connection")
    def test_test_smtp_connection_command_failure(self, mock_get_connection):
        mock_connection = mock_get_connection.return_value
        mock_connection.open.side_effect = OSError("connection refused")

        with self.assertRaises(CommandError):
            call_command("test_smtp_connection")

        mock_connection.close.assert_called_once()

    @override_settings(
        EMAIL_HOST="smtp.example.com",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="apikey",
        EMAIL_HOST_PASSWORD="secret",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        EMAIL_TIMEOUT=20,
    )
    @patch("dataviz.management.commands.test_smtp_connection.get_connection")
    def test_test_smtp_connection_command_skip_auth(self, mock_get_connection):
        mock_connection = mock_get_connection.return_value

        call_command("test_smtp_connection", "--skip-auth")

        kwargs = mock_get_connection.call_args.kwargs
        self.assertEqual(kwargs["username"], "")
        self.assertEqual(kwargs["password"], "")
        mock_connection.open.assert_called_once()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.sendgrid.net",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="apikey",
        EMAIL_HOST_PASSWORD="very-secret-token",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        EMAIL_TIMEOUT=20,
        DEFAULT_FROM_EMAIL="DataViz Pro <no-reply@dataviz.example>",
        SERVER_EMAIL="DataViz Pro <no-reply@dataviz.example>",
        PASSWORD_RESET_FROM_EMAIL="DataViz Pro Security <no-reply@dataviz.example>",
        PASSWORD_RESET_USE_HTTPS=True,
        PASSWORD_RESET_DOMAIN_OVERRIDE="dataviz.example.com",
    )
    def test_smtp_config_status_redacts_secrets(self):
        output = StringIO()

        call_command("smtp_config_status", stdout=output)

        status_text = output.getvalue()
        self.assertIn("SMTP_READY: yes", status_text)
        self.assertIn("PASSWORD_RESET_READY: yes", status_text)
        self.assertIn("EMAIL_HOST_USER: [set]", status_text)
        self.assertIn("EMAIL_HOST_PASSWORD: [set]", status_text)
        self.assertNotIn("very-secret-token", status_text)
        self.assertNotIn("apikey", status_text)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="",
        EMAIL_PORT=0,
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=True,
        DEFAULT_FROM_EMAIL="",
    )
    def test_smtp_config_status_strict_raises_when_not_ready(self):
        with self.assertRaises(CommandError):
            call_command("smtp_config_status", "--strict")

    def test_login_auto_subscribes_user_email_to_newsletter(self):
        user = get_user_model().objects.create_user(
            username="newsletter_login_user",
            email="newsletter-login@example.com",
            password="safe-pass-123",
        )

        self.client.post(
            reverse("login"),
            {
                "username": user.email,
                "password": "safe-pass-123",
                "next": reverse("dataviz:home"),
            },
        )

        self.assertTrue(
            NewsletterSubscriber.objects.filter(email="newsletter-login@example.com", is_active=True).exists()
        )

    def test_newsletter_subscribe_creates_subscriber(self):
        response = self.client.post(
            reverse("dataviz:newsletter_subscribe"),
            {
                "email": "subscriber@example.com",
                "next": reverse("dataviz:datasets"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dataviz:datasets"))
        self.assertTrue(
            NewsletterSubscriber.objects.filter(email="subscriber@example.com", is_active=True).exists()
        )

    @patch("dataviz.signals.send_newsletter_notification")
    def test_newsletter_sends_email_for_new_blog(self, mock_send_notification):
        Blog.objects.create(
            title="Quarterly Data Update",
            slug="quarterly-data-update",
            content="Latest data insights.",
        )

        mock_send_notification.assert_called_once()
        payload = mock_send_notification.call_args.kwargs
        self.assertIn("New blog post", payload["subject"])
        self.assertIn("quarterly-data-update", payload["body"])

    @patch("dataviz.signals.send_newsletter_notification")
    def test_newsletter_sends_email_for_new_dataset(self, mock_send_notification):
        StoredDataset.objects.create(
            title="Marketing Funnel 2026",
            description="Dataset for newsletter dataset notification",
            dataset_file=SimpleUploadedFile("newsletter_dataset.csv", b"a,b\n1,2\n", content_type="text/csv"),
            original_filename="newsletter_dataset.csv",
        )

        mock_send_notification.assert_called_once()
        payload = mock_send_notification.call_args.kwargs
        self.assertIn("New dataset added", payload["subject"])
        self.assertIn(reverse("dataviz:datasets"), payload["body"])

    def test_dataset_store_search_filter_sort_and_pagination(self):
        uploader = get_user_model().objects.create_user(username="owner_user", password="owner-pass-123")

        for idx in range(10):
            extension = "csv" if idx % 2 == 0 else "json"
            filename = f"sales_{idx}.{extension}"
            content = b"a,b\n1,2\n" if extension == "csv" else b"[{\"a\":1,\"b\":2}]"
            content_type = "text/csv" if extension == "csv" else "application/json"

            StoredDataset.objects.create(
                title=f"Sales {idx}",
                description="Regional performance dataset",
                dataset_file=SimpleUploadedFile(filename, content, content_type=content_type),
                original_filename=filename,
                uploaded_by=uploader if idx % 3 == 0 else None,
            )

        StoredDataset.objects.create(
            title="Inventory Archive",
            description="Warehouse stock snapshot",
            dataset_file=SimpleUploadedFile("inventory.csv", b"a,b\n3,4\n", content_type="text/csv"),
            original_filename="inventory.csv",
        )

        response = self.client.get(
            reverse("dataviz:datasets"),
            {
                "q": "Sales",
                "file_type": "csv",
                "sort": "title_desc",
            },
        )

        self.assertEqual(response.status_code, 200)
        page_obj = response.context["store_page_obj"]
        self.assertGreaterEqual(page_obj.paginator.num_pages, 1)

        listed_titles = [item.title for item in page_obj.object_list]
        self.assertTrue(all(title.startswith("Sales") for title in listed_titles))
        self.assertEqual(listed_titles, sorted(listed_titles, reverse=True))
        self.assertTrue(all(item.download_name.lower().endswith(".csv") for item in page_obj.object_list))

    def test_dataset_store_upload_persists_tags(self):
        user = get_user_model().objects.create_user(
            username="tagger",
            is_staff=True,
        )
        self.client.force_login(user)

        upload = SimpleUploadedFile("finance_report.csv", b"a,b\n1,2\n", content_type="text/csv")
        response = self.client.post(
            reverse("dataviz:datasets"),
            {
                "store_dataset_submit": "1",
                "store_title": "Finance Report",
                "store_description": "Quarterly finance report",
                "store_tags": "finance, quarterly, CFO",
                "store_file_upload": upload,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        dataset = StoredDataset.objects.get(title="Finance Report")
        tag_names = set(dataset.tags.values_list("name", flat=True))
        self.assertSetEqual(tag_names, {"finance", "quarterly", "CFO"})

    def test_non_admin_user_cannot_upload_to_shared_store(self):
        user = get_user_model().objects.create_user(username="member")
        self.client.force_login(user)

        upload = SimpleUploadedFile("blocked.csv", b"a,b\n1,2\n", content_type="text/csv")
        response = self.client.post(
            reverse("dataviz:datasets"),
            {
                "store_dataset_submit": "1",
                "store_title": "Blocked Upload",
                "store_description": "Should be blocked for non-admin users",
                "store_file_upload": upload,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You do not have permission to publish datasets to the shared store")
        self.assertFalse(StoredDataset.objects.filter(title="Blocked Upload").exists())

    def test_non_admin_user_cannot_upload_dataset_from_dataset_page(self):
        user = get_user_model().objects.create_user(username="viewer")
        self.client.force_login(user)

        upload = SimpleUploadedFile("private.csv", b"a,b\n3,4\n", content_type="text/csv")
        response = self.client.post(
            reverse("dataviz:datasets"),
            {
                "file_upload": upload,
                "dataset_explanation": "Should not be accepted",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You do not have permission to upload datasets from this page")

    def test_dataset_store_relevance_sort_prioritizes_exact_title(self):
        finance_tag = DatasetTag.objects.create(name="finance")

        exact = StoredDataset.objects.create(
            title="Sales Forecast",
            description="Exact title match dataset",
            dataset_file=SimpleUploadedFile("exact.csv", b"a,b\n1,2\n", content_type="text/csv"),
            original_filename="exact.csv",
        )
        exact.tags.add(finance_tag)

        partial = StoredDataset.objects.create(
            title="Monthly Sales Performance",
            description="Contains sales mention",
            dataset_file=SimpleUploadedFile("partial.csv", b"a,b\n3,4\n", content_type="text/csv"),
            original_filename="partial.csv",
        )
        partial.tags.add(finance_tag)

        response = self.client.get(reverse("dataviz:datasets"), {"q": "Sales", "sort": "relevance"})

        self.assertEqual(response.status_code, 200)
        titles = [dataset.title for dataset in response.context["store_page_obj"].object_list]
        self.assertGreaterEqual(len(titles), 2)
        self.assertEqual(titles[0], "Sales Forecast")

    def test_dataset_store_tag_filter_only_returns_matching_tag(self):
        finance_tag = DatasetTag.objects.create(name="finance")
        healthcare_tag = DatasetTag.objects.create(name="healthcare")

        finance_dataset = StoredDataset.objects.create(
            title="Finance KPI",
            description="Finance data",
            dataset_file=SimpleUploadedFile("finance.csv", b"a,b\n5,6\n", content_type="text/csv"),
            original_filename="finance.csv",
        )
        finance_dataset.tags.add(finance_tag)

        healthcare_dataset = StoredDataset.objects.create(
            title="Healthcare KPI",
            description="Healthcare data",
            dataset_file=SimpleUploadedFile("health.csv", b"a,b\n7,8\n", content_type="text/csv"),
            original_filename="health.csv",
        )
        healthcare_dataset.tags.add(healthcare_tag)

        response = self.client.get(reverse("dataviz:datasets"), {"tag": finance_tag.slug})

        self.assertEqual(response.status_code, 200)
        titles = [dataset.title for dataset in response.context["store_page_obj"].object_list]
        self.assertIn("Finance KPI", titles)
        self.assertNotIn("Healthcare KPI", titles)


class DataProcessorNormalizationTests(TestCase):
    def test_market_matrix_csv_is_normalized_to_numeric_columns(self):
        csv_payload = (
            "Price,Close,Close.1,Close.2,High,High.1,High.2\n"
            "Ticker,BYDDF,TM,TSLA,BYDDF,TM,TSLA\n"
            "Date,,,,,,\n"
            "2018-01-02,2.85,104.70,21.36,2.88,104.74,21.47\n"
            "2018-01-03,2.95,106.13,21.15,2.95,106.22,21.68\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "market.csv")
            with open(file_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(csv_payload)

            df, error = data_processor.load_dataset(file_path=file_path)

        self.assertIsNone(error)
        self.assertEqual(df.shape[0], 2)
        self.assertIn("Date", df.columns)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["Date"]))

        numeric_columns = data_processor.get_numeric_columns(df)
        self.assertGreaterEqual(len(numeric_columns), 3)
        self.assertIn("Close_BYDDF", numeric_columns)
        self.assertIn("Close_TM", numeric_columns)

    def test_geo_choropleth_auto_detects_iso3_and_colors_countries(self):
        df = pd.DataFrame({
            "Country": ["CHN", "IND", "USA", "JPN"],
        })

        html, error = data_processor.generate_advanced_plotly_plot(
            df,
            plot_type="Geo Choropleth",
            location_col="Country",
            geo_location_mode="country names",
            geo_choropleth_color_scale="Viridis",
        )

        self.assertIsNone(error)
        self.assertIsNotNone(html)
        self.assertIn('"locationmode":"ISO-3"', html)
        self.assertIn('"CHN"', html)

    def test_geo_scatter_auto_detects_iso3_location_mode(self):
        df = pd.DataFrame({
            "Country": ["CHN", "IND", "USA", "JPN"],
            "Value": [1, 2, 3, 4],
        })

        html, error = data_processor.generate_advanced_plotly_plot(
            df,
            plot_type="Geo Scatter",
            location_col="Country",
            size_col="Value",
            geo_location_mode="country names",
        )

        self.assertIsNone(error)
        self.assertIsNotNone(html)
        self.assertIn('"locationmode":"ISO-3"', html)

    def test_sql_script_file_is_loaded_into_dataframe(self):
        sql_payload = (
            "CREATE TABLE sales (id INTEGER, amount REAL, region TEXT);\n"
            "INSERT INTO sales VALUES (1, 120.5, 'North');\n"
            "INSERT INTO sales VALUES (2, 180.0, 'South');\n"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "sample.sql")
            with open(file_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(sql_payload)

            df, error = data_processor.load_dataset(file_path=file_path)

        self.assertIsNone(error)
        self.assertEqual(df.shape[0], 2)
        self.assertIn("amount", df.columns)
        self.assertIn("region", df.columns)

    def test_get_analyst_brief_returns_quality_and_recommendations(self):
        df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-03"],
                "sales": [100, 120, None, 120],
                "profit": [20, 30, 40, 30],
                "region": ["North", "South", "South", "South"],
            }
        )

        brief = data_processor.get_analyst_brief(df)

        self.assertIn("snapshot_cards", brief)
        self.assertIn("quality_signals", brief)
        self.assertIn("recommendations", brief)
        self.assertGreaterEqual(len(brief["snapshot_cards"]), 4)
        self.assertGreaterEqual(len(brief["quality_signals"]), 1)
        self.assertGreaterEqual(len(brief["recommendations"]), 1)

    def test_get_metric_anomaly_alerts_detects_spike(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=12, freq="D"),
                "sales": [100, 102, 98, 101, 99, 100, 103, 101, 102, 305, 101, 99],
            }
        )

        alerts = data_processor.get_metric_anomaly_alerts(df, metric_col="sales", date_col="date")

        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["metric"], "sales")
        self.assertIn(alerts[0]["direction"], ["spike", "drop"])

    def test_get_chart_suggestions_prefers_line_for_date_and_metric(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=8, freq="D"),
                "sales": [100, 102, 99, 104, 103, 105, 107, 108],
                "region": ["North", "South", "North", "South", "North", "South", "North", "South"],
            }
        )

        suggestions = data_processor.get_chart_suggestions(df, x_col="date", y_col="sales")
        plot_types = [item["plot_type"] for item in suggestions]

        self.assertIn("Line", plot_types)
        self.assertIn("Histogram", plot_types)

    def test_get_dashboard_command_center_returns_kpi_cards(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=6, freq="D"),
                "sales": [100, 120, 140, 160, 180, 200],
                "profit": [10, 18, 24, 28, 34, 40],
                "region": ["North", "North", "South", "South", "East", "East"],
            }
        )

        command_center = data_processor.get_dashboard_command_center(
            df,
            metric_col="sales",
            secondary_metric_col="profit",
            category_col="region",
            date_col="date",
        )

        self.assertIn("cards", command_center)
        self.assertGreaterEqual(len(command_center["cards"]), 4)
        self.assertIn("coverage_summary", command_center)
        self.assertIn("top_category_summary", command_center)

    def test_geo_choropleth_supports_year_animation_and_trend_line(self):
        df = pd.DataFrame({
            "Country": ["USA", "USA", "CAN", "CAN"],
            "Sales": [120, 180, 80, 140],
            "Year": [2021, 2022, 2021, 2022],
        })

        html, error = data_processor.generate_advanced_plotly_plot(
            df,
            plot_type="Geo Choropleth",
            location_col="Country",
            size_col="Sales",
            animation_col="Year",
            geo_location_mode="ISO-3",
        )

        self.assertIsNone(error)
        self.assertIsNotNone(html)
        self.assertIn('Plotly.addFrames', html)
        self.assertIn('_animation_frame=2021', html)
        self.assertIn('_animation_frame=2022', html)
        self.assertIn('Year-wise Performance (Sales)', html)

    @patch("dataviz.views.data_processor.generate_dashboard_panels")
    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_dashboard_can_render_four_panels(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        _mock_plot,
        mock_dashboard,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "sales": [100, 120, 140, 180],
                "profit": [20, 25, 31, 44],
                "store": ["A", "B", "A", "B"],
                "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            }),
            None,
        )
        mock_dashboard.return_value = [
            {"title": "Chart 1", "html": "<div>chart-1</div>", "note": "n1"},
            {"title": "Chart 2", "html": "<div>chart-2</div>", "note": "n2"},
            {"title": "Chart 3", "html": "<div>chart-3</div>", "note": "n3"},
            {"title": "Chart 4", "html": "<div>chart-4</div>", "note": "n4"},
        ]

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_metric_select": "sales",
                "dashboard_secondary_metric_select": "profit",
                "dashboard_category_select": "store",
                "dashboard_date_select": "date",
                "dashboard_panel_count_select": "4",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Dashboard")
        self.assertContains(response, "Dashboard Command Center")
        self.assertContains(response, "Chart 4")
        self.assertEqual(mock_dashboard.call_args.kwargs["panel_count"], 4)

    @patch("dataviz.views.data_processor.generate_dashboard_panels")
    @patch("dataviz.views.data_processor.infer_dashboard_preset_config")
    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_apply_preset_autofills_dashboard_selections(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        _mock_plot,
        mock_infer,
        mock_dashboard,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "sales": [100, 120, 140, 180],
                "profit": [20, 25, 31, 44],
                "store": ["A", "B", "A", "B"],
                "order_date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            }),
            None,
        )
        mock_infer.return_value = {
            "metric": "sales",
            "secondary_metric": "profit",
            "category": "store",
            "date": "order_date",
            "panel_count": 6,
        }
        mock_dashboard.return_value = [
            {"title": "Preset Chart 1", "html": "<div>preset-chart-1</div>", "note": "n1"},
            {"title": "Preset Chart 2", "html": "<div>preset-chart-2</div>", "note": "n2"},
        ]

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_preset_select": "retail_sales",
                "apply_dashboard_preset": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applied preset: Retail Sales Dashboard")
        self.assertContains(response, "Preset Chart 1")

        kwargs = mock_dashboard.call_args.kwargs
        self.assertEqual(kwargs["metric_col"], "sales")
        self.assertEqual(kwargs["secondary_metric_col"], "profit")
        self.assertEqual(kwargs["category_col"], "store")
        self.assertEqual(kwargs["date_col"], "order_date")
        self.assertEqual(kwargs["panel_count"], 6)
        self.assertEqual(kwargs["preset_key"], "retail_sales")
        self.assertIsInstance(kwargs["stage_order"], str)

    @patch("dataviz.views.data_processor.generate_dashboard_panels")
    @patch("dataviz.views.data_processor.infer_dashboard_preset_config")
    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_ecommerce_funnel_preset_autofill_and_forwarding(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        _mock_plot,
        mock_infer,
        mock_dashboard,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "sessions": [1200, 900, 650, 420],
                "orders": [120, 95, 80, 60],
                "funnel_stage": ["Visit", "Product View", "Add to Cart", "Purchase"],
                "event_date": ["2024-02-01", "2024-02-01", "2024-02-01", "2024-02-01"],
            }),
            None,
        )
        mock_infer.return_value = {
            "metric": "sessions",
            "secondary_metric": "orders",
            "category": "funnel_stage",
            "date": "event_date",
            "panel_count": 6,
        }
        mock_dashboard.return_value = [
            {"title": "Funnel Chart 1", "html": "<div>funnel-chart-1</div>", "note": "n1"},
        ]

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_preset_select": "ecommerce_funnel",
                "apply_dashboard_preset": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E-commerce Funnel Dashboard")
        self.assertContains(response, "Applied preset: E-commerce Funnel Dashboard")
        self.assertContains(response, "Move to Start")
        self.assertContains(response, "Move Left")
        self.assertContains(response, "Move Right")
        self.assertContains(response, "Move to End")
        self.assertContains(response, "Keyboard Tips")
        self.assertContains(response, "Home")
        self.assertContains(response, "End")
        self.assertContains(response, "Esc")
        self.assertContains(response, "Saved per preset")
        self.assertContains(response, "Toast stays pinned while keyboard reordering is active")
        self.assertContains(response, "Funnel stage order chip board")
        self.assertContains(response, "Clear Saved (This Preset)")
        self.assertContains(response, "Stage Action Status")
        self.assertContains(response, "funnelStageToastIcon")
        self.assertContains(response, "funnelStageToastTimer")

        kwargs = mock_dashboard.call_args.kwargs
        self.assertEqual(kwargs["metric_col"], "sessions")
        self.assertEqual(kwargs["secondary_metric_col"], "orders")
        self.assertEqual(kwargs["category_col"], "funnel_stage")
        self.assertEqual(kwargs["date_col"], "event_date")
        self.assertEqual(kwargs["panel_count"], 6)
        self.assertEqual(kwargs["preset_key"], "ecommerce_funnel")
        self.assertIn("Visit", kwargs["stage_order"])

    @patch("dataviz.views.data_processor.generate_dashboard_panels")
    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_manual_funnel_stage_order_is_forwarded(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        _mock_plot,
        mock_dashboard,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "sessions": [1200, 900, 650, 420],
                "orders": [120, 95, 80, 60],
                "funnel_stage": ["Visit", "Product View", "Add to Cart", "Purchase"],
                "event_date": ["2024-02-01", "2024-02-01", "2024-02-01", "2024-02-01"],
            }),
            None,
        )
        mock_dashboard.return_value = [
            {"title": "Funnel Manual Chart", "html": "<div>funnel-manual-chart</div>", "note": "n1"},
        ]

        response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_preset_select": "ecommerce_funnel",
                "dashboard_metric_select": "sessions",
                "dashboard_secondary_metric_select": "orders",
                "dashboard_category_select": "funnel_stage",
                "dashboard_date_select": "event_date",
                "dashboard_panel_count_select": "6",
                "dashboard_stage_order_input": "Visit, Product View, Add to Cart, Purchase",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funnel Stage Order")

        kwargs = mock_dashboard.call_args.kwargs
        self.assertEqual(kwargs["preset_key"], "ecommerce_funnel")
        self.assertEqual(
            kwargs["stage_order"],
            "Visit, Product View, Add to Cart, Purchase",
        )

        stage_order_by_preset = self.client.session.get("dashboard_stage_order_by_preset", {})
        self.assertEqual(
            stage_order_by_preset.get("ecommerce_funnel"),
            "Visit, Product View, Add to Cart, Purchase",
        )

    @patch("dataviz.views.data_processor.generate_dashboard_panels")
    @patch("dataviz.views.data_processor.generate_interactive_plot", return_value=("plot", None))
    @patch("dataviz.views.data_processor.generate_correlation_heatmap", return_value=("heatmap", None))
    @patch("dataviz.views.data_processor.generate_pairplot", return_value=("pair", None))
    @patch("dataviz.views.data_processor.load_dataset")
    def test_stage_order_persists_per_preset_in_session(
        self,
        mock_load_dataset,
        _mock_pairplot,
        _mock_heatmap,
        _mock_plot,
        mock_dashboard,
    ):
        mock_load_dataset.return_value = (
            pd.DataFrame({
                "sessions": [1200, 900, 650, 420],
                "orders": [120, 95, 80, 60],
                "sales": [100, 120, 140, 180],
                "profit": [20, 25, 31, 44],
                "funnel_stage": ["Visit", "Product View", "Add to Cart", "Purchase"],
                "store": ["A", "A", "B", "B"],
                "event_date": ["2024-02-01", "2024-02-01", "2024-02-01", "2024-02-01"],
            }),
            None,
        )
        mock_dashboard.return_value = [
            {"title": "Chart", "html": "<div>chart</div>", "note": "n1"},
        ]

        first_response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_preset_select": "ecommerce_funnel",
                "dashboard_metric_select": "sessions",
                "dashboard_secondary_metric_select": "orders",
                "dashboard_category_select": "funnel_stage",
                "dashboard_date_select": "event_date",
                "dashboard_panel_count_select": "6",
                "dashboard_stage_order_input": "Visit, Product View, Add to Cart, Purchase",
            },
        )
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_preset_select": "retail_sales",
                "dashboard_metric_select": "sales",
                "dashboard_secondary_metric_select": "profit",
                "dashboard_category_select": "store",
                "dashboard_date_select": "event_date",
                "dashboard_panel_count_select": "4",
                "dashboard_stage_order_input": "Lead, Qualified, Closed",
            },
        )
        self.assertEqual(second_response.status_code, 200)

        third_response = self.client.post(
            reverse("dataviz:data_analysis"),
            {
                "dashboard_preset_select": "ecommerce_funnel",
                "dashboard_metric_select": "sessions",
                "dashboard_secondary_metric_select": "orders",
                "dashboard_category_select": "funnel_stage",
                "dashboard_date_select": "event_date",
                "dashboard_panel_count_select": "6",
            },
        )
        self.assertEqual(third_response.status_code, 200)

        kwargs = mock_dashboard.call_args.kwargs
        self.assertEqual(kwargs["preset_key"], "ecommerce_funnel")
        self.assertEqual(
            kwargs["stage_order"],
            "Visit, Product View, Add to Cart, Purchase",
        )

        stage_order_by_preset = self.client.session.get("dashboard_stage_order_by_preset", {})
        self.assertEqual(
            stage_order_by_preset.get("retail_sales"),
            "Lead, Qualified, Closed",
        )
        self.assertEqual(
            stage_order_by_preset.get("ecommerce_funnel"),
            "Visit, Product View, Add to Cart, Purchase",
        )
