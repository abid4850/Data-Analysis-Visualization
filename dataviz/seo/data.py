DATA_TYPES = [
    "sales", "finance", "marketing", "healthcare", "education",
    "ecommerce", "startup", "customer", "survey", "product",
]

CHART_TYPES = [
    "bar-charts", "line-charts", "pie-charts", "scatter-plots",
    "histograms", "dashboards", "heatmaps", "time-series",
    "box-plots", "area-charts",
]

# Priority pages targeted for richer programmatic SEO content.
TOP_PRIORITY_SEO_SLUGS = [
    "visualize-sales-data-with-bar-charts",
    "visualize-sales-data-with-line-charts",
    "visualize-sales-data-with-dashboards",
    "visualize-sales-data-with-time-series",
    "visualize-finance-data-with-line-charts",
    "visualize-finance-data-with-dashboards",
    "visualize-finance-data-with-heatmaps",
    "visualize-finance-data-with-box-plots",
    "visualize-marketing-data-with-bar-charts",
    "visualize-marketing-data-with-scatter-plots",
    "visualize-marketing-data-with-dashboards",
    "visualize-ecommerce-data-with-dashboards",
    "visualize-ecommerce-data-with-time-series",
    "visualize-ecommerce-data-with-scatter-plots",
    "visualize-customer-data-with-scatter-plots",
    "visualize-customer-data-with-heatmaps",
    "visualize-customer-data-with-line-charts",
    "visualize-product-data-with-dashboards",
    "visualize-healthcare-data-with-line-charts",
    "visualize-startup-data-with-dashboards",
]


def _build_priority_content(data_label, chart_label):
    return {
        "value_proposition": (
            f"This guide is designed for teams who need reliable {data_label} reporting with "
            f"{chart_label}. Use it to decide faster, communicate clearly, and avoid dashboard noise."
        ),
        "business_questions": [
            f"Which segments are driving {data_label} growth over time?",
            f"Where are we seeing unusual changes in {data_label} performance?",
            f"Which teams, regions, or products need intervention first?",
            f"What should be highlighted in the weekly executive snapshot?",
        ],
        "kpi_ideas": [
            f"Total {data_label} value",
            f"{data_label.capitalize()} growth rate",
            "Top category contribution",
            "Period-over-period delta",
        ],
        "recommended_columns": [
            "Date or time column",
            f"Primary {data_label} metric",
            "Category or segment",
            "Geography or region",
            "Owner or team",
        ],
        "workflow_steps": [
            "Upload CSV, XLSX, JSON, or SQL export.",
            "Select the metric and segmentation columns.",
            f"Apply {chart_label} and validate outliers.",
            "Export summary insights for stakeholders.",
            "Save recurring checks for the next reporting cycle.",
        ],
        "faqs": [
            {
                "question": f"What is the best chart for {data_label} trends?",
                "answer": (
                    f"Start with {chart_label} for directional patterns, then add segmentation "
                    "to compare categories and identify where performance changed."
                ),
            },
            {
                "question": "How much data should I upload for fast analysis?",
                "answer": (
                    "Use a clean recent slice first to validate metric behavior, then scale to the "
                    "full dataset once dimensions and filters are confirmed."
                ),
            },
            {
                "question": "How do I present insights to leadership quickly?",
                "answer": (
                    "Use a KPI summary, one trend visual, one variance visual, and a short action list "
                    "with owners and dates."
                ),
            },
        ],
    }


def _split_slug(slug):
    core = slug.replace("visualize-", "", 1)
    data_name, chart_name = core.split("-data-with-", maxsplit=1)
    return data_name, chart_name


SEO_PAGES = []

for data_name in DATA_TYPES:
    for chart_name in CHART_TYPES:
        slug = f"visualize-{data_name}-data-with-{chart_name}"
        chart_label = chart_name.replace('-', ' ')
        page = {
            "slug": slug,
            "title": f"Visualize {data_name.capitalize()} Data with {chart_label.title()}",
            "description": (
                f"Learn how to visualize {data_name} data using {chart_label} "
                "with an online data visualization tool."
            ),
            "h1": f"Visualize {data_name.capitalize()} Data Using {chart_label.title()}",
            "intro": (
                f"{data_name.capitalize()} data visualization helps uncover trends and insights. "
                f"Using {chart_label}, you can quickly understand patterns and performance."
            ),
            "use_cases": [
                f"Analyze {data_name} trends",
                f"Monitor {data_name} performance",
                f"Create {data_name} dashboards",
            ],
            "is_priority": slug in TOP_PRIORITY_SEO_SLUGS,
        }

        if page["is_priority"]:
            page.update(_build_priority_content(data_name, chart_label))

        SEO_PAGES.append(page)


SEO_PAGE_BY_SLUG = {page["slug"]: page for page in SEO_PAGES}

for page in SEO_PAGES:
    if not page.get("is_priority"):
        page["related_pages"] = []
        continue

    data_name, chart_name = _split_slug(page["slug"])

    same_data = [
        slug for slug in TOP_PRIORITY_SEO_SLUGS
        if slug != page["slug"] and _split_slug(slug)[0] == data_name
    ]
    same_chart = [
        slug for slug in TOP_PRIORITY_SEO_SLUGS
        if slug != page["slug"] and _split_slug(slug)[1] == chart_name
    ]

    ranked_related = []
    for slug in same_data + same_chart + TOP_PRIORITY_SEO_SLUGS:
        if slug == page["slug"] or slug in ranked_related:
            continue
        ranked_related.append(slug)
        if len(ranked_related) >= 4:
            break

    page["related_pages"] = [
        {
            "slug": slug,
            "title": SEO_PAGE_BY_SLUG[slug]["title"],
        }
        for slug in ranked_related
    ]
