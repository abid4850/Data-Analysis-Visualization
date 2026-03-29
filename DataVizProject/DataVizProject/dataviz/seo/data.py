DATA_TYPES = [
    "sales", "finance", "marketing", "healthcare", "education",
    "ecommerce", "startup", "customer", "survey", "product",
]

CHART_TYPES = [
    "bar-charts", "line-charts", "pie-charts", "scatter-plots",
    "histograms", "dashboards", "heatmaps", "time-series",
    "box-plots", "area-charts",
]

SEO_PAGES = []

for data in DATA_TYPES:
    for chart in CHART_TYPES:
        slug = f"visualize-{data}-data-with-{chart}"
        SEO_PAGES.append({
            "slug": slug,
            "title": f"Visualize {data.capitalize()} Data with {chart.replace('-', ' ').title()}",
            "description": f"Learn how to visualize {data} data using {chart.replace('-', ' ')} with an online data visualization tool.",
            "h1": f"Visualize {data.capitalize()} Data Using {chart.replace('-', ' ').title()}",
            "intro": f"{data.capitalize()} data visualization helps uncover trends and insights. Using {chart.replace('-', ' ')}, you can quickly understand patterns and performance.",
            "use_cases": [
                f"Analyze {data} trends",
                f"Monitor {data} performance",
                f"Create {data} dashboards"
            ]
        })
