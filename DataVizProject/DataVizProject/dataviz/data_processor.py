# ===== data_processor.py (updated/fault-tolerant) =====
import io
import os
import base64
import pandas as pd
import numpy as np
import matplotlib
# Use non-interactive backend to avoid GUI/Tk issues
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objs as go
import plotly.io as pio

# Common dataset options (seaborn sample datasets)
DATASET_OPTIONS = [
    'iris', 'tips', 'penguins', 'flights', 'titanic', 'car_crashes'
]


def load_dataset(file_path: str = None, sample_name: str = 'iris'):
    """Load a dataset from a file path (csv/xlsx) or seaborn sample dataset.
    Returns: (DataFrame, error_message_or_None)
    """
    try:
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ['.csv']:
                df = pd.read_csv(file_path)
            elif ext in ['.xls', '.xlsx']:
                df = pd.read_excel(file_path)
            else:
                return pd.DataFrame(), f"Unsupported file extension: {ext}"
            return df, None

        # Load default seaborn dataset
        try:
            df = sns.load_dataset(sample_name)
        except Exception:
            # fallback to iris if seaborn dataset fails
            df = sns.load_dataset('iris')
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


def get_data_overview(df: pd.DataFrame):
    """Return a dict with shape, preview (html), dtypes (html), missing values and summary stats."""
    try:
        preview = df.head().to_html(classes='table table-sm table-striped', index=False)
        dtypes = df.dtypes.to_frame('dtype').to_html(classes='table table-sm', header=True)
        missing = None
        if df.isnull().values.any():
            missing = df.isnull().sum().to_frame('missing_count').to_html(classes='table table-sm')
        summary = None
        if df.select_dtypes(include=[np.number]).shape[1] > 0:
            summary = df.describe().to_html(classes='table table-sm')

        return {
            'shape': df.shape,
            'preview': preview,
            'dtypes': dtypes,
            'missing_values': missing,
            'summary_stats': summary,
        }
    except Exception as e:
        return {'shape': (0, 0), 'preview': '', 'dtypes': '', 'missing_values': '', 'summary_stats': '', 'error': str(e)}


def get_numeric_columns(df: pd.DataFrame):
    return df.select_dtypes(include=[np.number]).columns.tolist()


def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode('ascii')
    return encoded


def generate_pairplot(df: pd.DataFrame, hue: str = None):
    """Generate seaborn pairplot and return as base64 PNG string."""
    try:
        numeric = get_numeric_columns(df)
        if len(numeric) < 2:
            return None, 'Pairplot requires at least two numeric columns.'

        # to avoid overly large pairplots, limit to first 6 numeric columns
        cols = numeric[:6]
        pair = sns.pairplot(df[cols + ([hue] if hue and hue in df.columns else [])], hue=hue)
        fig = pair.fig
        img_b64 = _fig_to_base64(fig)
        return img_b64, None
    except Exception as e:
        try:
            plt.close('all')
        except Exception:
            pass
        return None, str(e)


def generate_correlation_heatmap(df: pd.DataFrame):
    """Return an interactive Plotly heatmap HTML snippet (not full HTML page)."""
    try:
        num = df.select_dtypes(include=[np.number])
        if num.shape[1] == 0:
            return None, 'No numeric columns for correlation heatmap.'

        corr = num.corr()
        fig = go.Figure(data=go.Heatmap(
            z=corr.values,
            x=corr.columns.tolist(),
            y=corr.index.tolist(),
            colorscale='Viridis',
            zmin=-1, zmax=1
        ))
        fig.update_layout(width=700, height=600, margin=dict(l=50, r=50, t=30, b=30))
        html = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')
        return html, None
    except Exception as e:
        return None, str(e)


def generate_interactive_plot(df: pd.DataFrame, x_col: str, y_col: str, plot_type: str, hue: str = None):
    """Generate a plot (PNG) for requested columns and return base64 PNG string."""
    try:
        if x_col not in df.columns or y_col not in df.columns:
            return None, 'Selected columns not found in dataset.'

        fig, ax = plt.subplots(figsize=(8, 5))

        if plot_type == 'Line':
            sns.lineplot(data=df, x=x_col, y=y_col, hue=hue, ax=ax)
        elif plot_type == 'Bar':
            sns.barplot(data=df, x=x_col, y=y_col, hue=hue, ax=ax)
        elif plot_type == 'Scatter':
            sns.scatterplot(data=df, x=x_col, y=y_col, hue=hue, ax=ax)
        elif plot_type == 'Histogram':
            # histogram of y
            sns.histplot(data=df, x=y_col, hue=hue, ax=ax)
        elif plot_type == 'KDE':
            sns.kdeplot(data=df, x=y_col, hue=hue, ax=ax, fill=True)
        else:
            # fallback to scatter
            sns.scatterplot(data=df, x=x_col, y=y_col, hue=hue, ax=ax)

        ax.set_title(f"{plot_type}: {y_col} vs {x_col}")
        plt.tight_layout()
        img_b64 = _fig_to_base64(fig)
        return img_b64, None
    except Exception as e:
        try:
            plt.close('all')
        except Exception:
            pass
        return None, str(e)

# End of dataprocessor
