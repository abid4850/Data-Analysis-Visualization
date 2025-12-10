from django.shortcuts import render
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import pandas as pd
import os
from . import data_processor


def home(request):
    # Pass dataset options for dropdown on home page
    context = {
        'dataset_options': data_processor.DATASET_OPTIONS,
        'selected_dataset': request.session.get('selected_dataset', None),
        'uploaded_file_name': request.session.get('uploaded_file_name', None),
    }
    return render(request, 'dataviz/home.html', context)


def get_dataframe(request):
    df = pd.DataFrame()
    error = None

    uploaded_file_path = request.session.get('uploaded_file_path')
    if uploaded_file_path and os.path.exists(uploaded_file_path):
        df, error = data_processor.load_dataset(file_path=uploaded_file_path)
        if not df.empty:
            return df, error

    sample_name = request.session.get('selected_dataset', 'iris')
    df, error = data_processor.load_dataset(sample_name=sample_name)

    return df, error


def data_analysis(request):
    # Chart types exposed to templates
    chart_types = ["Line", "Bar", "Scatter", "Histogram", "KDE"]

    # Dark mode preference
    dark_mode = request.session.get('dark_mode', False)

    context = {
        'dataset_options': data_processor.DATASET_OPTIONS,
        'selected_dataset': request.session.get('selected_dataset', 'iris'),
        'uploaded_file_name': request.session.get('uploaded_file_name'),
        'plot_type': 'Scatter',
        'x_col': None,
        'y_col': None,
        'hue_col': None,
        'chart_types': chart_types,
        'dark_mode': dark_mode,
    }

    if request.method == 'POST':
        # Dark mode toggle
        if request.POST.get('toggle_dark'):
            current = request.session.get('dark_mode', False)
            request.session['dark_mode'] = not current
            context['dark_mode'] = request.session['dark_mode']

        # Dataset selection from dropdown
        if 'dataset_select' in request.POST:
            selected_dataset = request.POST.get('dataset_select')
            request.session['selected_dataset'] = selected_dataset
            request.session['uploaded_file_path'] = None
            request.session['uploaded_file_name'] = None
            context['selected_dataset'] = selected_dataset

        # File upload handling
        elif 'file_upload' in request.FILES:
            uploaded_file = request.FILES['file_upload']
            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)
            uploaded_file_path = os.path.join(settings.MEDIA_ROOT, filename)

            request.session['uploaded_file_path'] = uploaded_file_path
            request.session['uploaded_file_name'] = uploaded_file.name
            request.session['selected_dataset'] = None
            context['uploaded_file_name'] = uploaded_file.name

        # Plot parameters update
        if 'x_col_select' in request.POST or 'hue_col_select' in request.POST:
            context['x_col'] = request.POST.get('x_col_select')
            context['y_col'] = request.POST.get('y_col_select')
            context['plot_type'] = request.POST.get('plot_type_select', context['plot_type'])
            context['hue_col'] = request.POST.get('hue_col_select')

    # Load the dataframe for analysis
    df, error = get_dataframe(request)

    if error:
        context['error'] = error
        return render(request, 'dataviz/analysis.html', context)

    if df.empty:
        context['info'] = "Please select a dataset or upload a file to begin analysis."
        return render(request, 'dataviz/analysis.html', context)

    # Data overview and columns
    context['overview'] = data_processor.get_data_overview(df)
    numeric_cols = data_processor.get_numeric_columns(df)
    context['numeric_columns'] = numeric_cols
    context['all_columns'] = df.columns.tolist()

    # Fix hue_col None value
    if context.get('hue_col') == 'None':
        context['hue_col'] = None

    # Generate pairplot
    pairplot_img, pairplot_error = data_processor.generate_pairplot(df, context.get('hue_col'))
    context['pairplot_img'] = pairplot_img
    context['pairplot_error'] = pairplot_error

    # Generate heatmap
    heatmap_html, heatmap_error = data_processor.generate_correlation_heatmap(df)
    context['heatmap_html'] = heatmap_html
    context['heatmap_error'] = heatmap_error

    # Generate interactive plot
    if context.get('x_col') and context.get('y_col') and context.get('plot_type'):
        plot_img, plot_error = data_processor.generate_interactive_plot(
            df, context['x_col'], context['y_col'], context['plot_type'], hue=context.get('hue_col')
        )
        context['interactive_plot_img'] = plot_img
        context['interactive_plot_error'] = plot_error
    elif numeric_cols:
        # sensible default columns if not selected
        context['x_col'] = context['x_col'] or numeric_cols[0]
        context['y_col'] = context['y_col'] or (numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0])
        plot_img, plot_error = data_processor.generate_interactive_plot(
            df, context['x_col'], context['y_col'], context['plot_type'], hue=context.get('hue_col')
        )
        context['interactive_plot_img'] = plot_img
        context['interactive_plot_error'] = plot_error

    return render(request, 'dataviz/analysis.html', context)
