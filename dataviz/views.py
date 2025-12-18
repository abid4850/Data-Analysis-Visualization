from django.shortcuts import render
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from .blog_data import BLOG_POSTS
from django.shortcuts import render, get_object_or_404
from django.http import Http404

import pandas as pd
import os

from . import data_processor


# -----------------------------
# Core Pages
# -----------------------------

def home(request):
    """Homepage with dataset selector"""
    context = {
        'dataset_options': data_processor.DATASET_OPTIONS,
        'selected_dataset': request.session.get('selected_dataset'),
        'uploaded_file_name': request.session.get('uploaded_file_name'),
    }
    return render(request, 'dataviz/home.html', context)


def features(request):
    return render(request, "dataviz/features.html")


def online_data_visualization(request):
    return render(request, "dataviz/online_data_visualization.html")


def python_data_visualization(request):
    return render(request, "dataviz/python_data_visualization.html")


def data_visualization_dashboard(request):
    return render(request, "dataviz/data_visualization_dashboard.html")

def blog_dynamic(request, slug):
    post = next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post:
       raise Http404()
    return render(request, "dataviz/blog/dynamic_post.html", {"post": post})

def compare_tableau(request):
    return render(request, "dataviz/compare/tableau.html")

def compare_powerbi(request):
    return render(request, "dataviz/compare/powerbi.html")

def csv_visualizer(request):
    return render(request, "dataviz/tools/csv_visualizer.html")

def dataset_summary(request):
    return render(request, "dataviz/tools/dataset_summary.html")

def chart_generator(request):
    return render(request, "dataviz/tools/chart_generator.html")

def data_visualization_examples(request):
    return render(request, 'dataviz/data_visualization_examples.html')

def data_visualization_cheat_sheet(request):
    return render(request, 'dataviz/data_visualization_cheat_sheet.html')

def python_visualization_examples(request):
    return render(request, 'dataviz/python_visualization_examples.html')

def visualize_sales_data(request):
    return render(request, 'dataviz/visualize_sales_data.html')

def visualize_financial_data(request):
    return render(request, 'dataviz/visualize_financial_data.html')

def visualize_healthcare_data(request):
    return render(request, 'dataviz/visualize_healthcare_data.html')

def datasets(request):
    return render(request, 'dataviz/datasets.html')

def global_sales_2024(request):
    return render(request, 'dataviz/global_sales_2024.html')

def student_performance_data(request):
    return render(request, 'dataviz/student_performance_data.html')

def about(request):
    return render(request, 'dataviz/about.html')

def dataviz_vs_excel(request):
    return render(request, 'dataviz/dataviz_vs_excel.html')

def dataviz_vs_google_sheets(request):
    return render(request, 'dataviz/dataviz_vs_google_sheets.html')

def dataviz_vs_plotly(request):
    return render(request, 'dataviz/dataviz_vs_plotly.html')

# -----------------------------
# Blog Pages
# -----------------------------

def blog_index(request):
    return render(request, "dataviz/blog/index.html")


def blog_upload_visualize(request):
    return render(request, "dataviz/blog/upload_data_and_visualize.html")


# -----------------------------
# Data Utilities
# -----------------------------

def get_dataframe(request):
    """
    Load dataframe from:
    1. Uploaded file (if exists)
    2. Selected sample dataset (fallback)
    """
    uploaded_file_path = request.session.get('uploaded_file_path')

    if uploaded_file_path and os.path.exists(uploaded_file_path):
        df, error = data_processor.load_dataset(file_path=uploaded_file_path)
        if not df.empty:
            return df, error

    sample_name = request.session.get('selected_dataset', 'iris')
    return data_processor.load_dataset(sample_name=sample_name)


# -----------------------------
# Analysis View
# -----------------------------

def data_analysis(request):
    """Main interactive analysis view"""

    chart_types = ["Line", "Bar", "Scatter", "Histogram", "KDE"]

    context = {
        'dataset_options': data_processor.DATASET_OPTIONS,
        'selected_dataset': request.session.get('selected_dataset', 'iris'),
        'uploaded_file_name': request.session.get('uploaded_file_name'),
        'plot_type': 'Scatter',
        'x_col': None,
        'y_col': None,
        'hue_col': None,
        'chart_types': chart_types,
        'dark_mode': request.session.get('dark_mode', False),
    }

    # -----------------------------
    # POST Handling
    # -----------------------------
    if request.method == 'POST':

        # Dark mode toggle
        if request.POST.get('toggle_dark'):
            request.session['dark_mode'] = not request.session.get('dark_mode', False)
            context['dark_mode'] = request.session['dark_mode']

        # Dataset selection
        if 'dataset_select' in request.POST:
            request.session['selected_dataset'] = request.POST.get('dataset_select')
            request.session['uploaded_file_path'] = None
            request.session['uploaded_file_name'] = None
            context['selected_dataset'] = request.session['selected_dataset']

        # File upload
        elif 'file_upload' in request.FILES:
            uploaded_file = request.FILES['file_upload']
            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)

            request.session['uploaded_file_path'] = os.path.join(settings.MEDIA_ROOT, filename)
            request.session['uploaded_file_name'] = uploaded_file.name
            request.session['selected_dataset'] = None

            context['uploaded_file_name'] = uploaded_file.name

        # Plot parameters
        context['x_col'] = request.POST.get('x_col_select')
        context['y_col'] = request.POST.get('y_col_select')
        context['plot_type'] = request.POST.get('plot_type_select', context['plot_type'])
        context['hue_col'] = request.POST.get('hue_col_select')

        if context['hue_col'] == 'None':
            context['hue_col'] = None

    # -----------------------------
    # Load Data
    # -----------------------------
    df, error = get_dataframe(request)

    if error:
        context['error'] = error
        return render(request, 'dataviz/analysis.html', context)

    if df.empty:
        context['info'] = "Please select a dataset or upload a file to begin analysis."
        return render(request, 'dataviz/analysis.html', context)

    # -----------------------------
    # Data Insights
    # -----------------------------
    context['overview'] = data_processor.get_data_overview(df)
    numeric_cols = data_processor.get_numeric_columns(df)

    context['numeric_columns'] = numeric_cols
    context['all_columns'] = df.columns.tolist()

    # Defaults if user hasn’t selected columns
    if numeric_cols:
        context['x_col'] = context['x_col'] or numeric_cols[0]
        context['y_col'] = context['y_col'] or (
            numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0]
        )

    # -----------------------------
    # Visualizations
    # -----------------------------
    context['pairplot_img'], context['pairplot_error'] = (
        data_processor.generate_pairplot(df, context['hue_col'])
    )

    context['heatmap_html'], context['heatmap_error'] = (
        data_processor.generate_correlation_heatmap(df)
    )

    context['interactive_plot_img'], context['interactive_plot_error'] = (
        data_processor.generate_interactive_plot(
            df,
            context['x_col'],
            context['y_col'],
            context['plot_type'],
            hue=context['hue_col'],
        )
    )

    return render(request, 'dataviz/analysis.html', context)
