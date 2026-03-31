# ===== data_processor.py (updated/fault-tolerant) =====
import io
import os
import base64
import re
import sqlite3
import pandas as pd
import numpy as np
import matplotlib
# Use non-interactive backend to avoid GUI/Tk issues
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objs as go
import plotly.io as pio
import plotly.express as px

# Common dataset options (seaborn sample datasets)
DATASET_OPTIONS = [
    'iris', 'tips', 'penguins', 'flights', 'titanic', 'car_crashes'
]

DASHBOARD_PRESETS = [
    {"value": "retail_sales", "label": "Retail Sales Dashboard"},
    {"value": "financial_kpi", "label": "Financial KPI Dashboard"},
    {"value": "operations", "label": "Operations Dashboard"},
    {"value": "ecommerce_funnel", "label": "E-commerce Funnel Dashboard"},
]


def get_dashboard_presets():
    return DASHBOARD_PRESETS


def _pick_by_tokens(columns, tokens, fallback=None):
    lowered = [(col, str(col).lower()) for col in columns]
    for token in tokens:
        for original, lowered_name in lowered:
            if token in lowered_name:
                return original
    return fallback


def infer_dashboard_preset_config(df: pd.DataFrame, preset_key: str, dashboard_options: dict):
    """Infer best dashboard columns for a business preset."""
    numeric_columns = dashboard_options.get('numeric_columns', [])
    category_columns = dashboard_options.get('category_columns', [])
    date_columns = dashboard_options.get('date_columns', [])

    default_metric = dashboard_options.get('default_metric')
    default_secondary = dashboard_options.get('default_secondary_metric')
    default_category = dashboard_options.get('default_category')
    default_date = dashboard_options.get('default_date')

    presets = {
        'retail_sales': {
            'metric_tokens': ['sales', 'revenue', 'amount', 'total', 'gmv', 'value', 'price'],
            'secondary_tokens': ['profit', 'margin', 'quantity', 'units', 'discount', 'cost'],
            'category_tokens': ['store', 'branch', 'region', 'category', 'segment', 'product', 'city'],
            'date_tokens': ['order_date', 'date', 'month', 'day', 'invoice_date', 'time'],
            'panel_count': 6,
        },
        'financial_kpi': {
            'metric_tokens': ['profit', 'net_income', 'revenue', 'cash', 'ebitda', 'amount'],
            'secondary_tokens': ['expense', 'cost', 'liability', 'assets', 'margin', 'opex'],
            'category_tokens': ['department', 'account', 'cost_center', 'region', 'segment', 'division'],
            'date_tokens': ['date', 'period', 'month', 'quarter', 'year', 'time'],
            'panel_count': 6,
        },
        'operations': {
            'metric_tokens': ['throughput', 'output', 'orders', 'volume', 'quantity', 'utilization', 'delivery'],
            'secondary_tokens': ['defect', 'downtime', 'delay', 'backlog', 'inventory', 'cost', 'lead_time'],
            'category_tokens': ['site', 'plant', 'warehouse', 'line', 'team', 'shift', 'region'],
            'date_tokens': ['date', 'timestamp', 'time', 'day', 'week', 'month'],
            'panel_count': 4,
        },
        'ecommerce_funnel': {
            'metric_tokens': ['sessions', 'traffic', 'visits', 'users', 'impressions', 'views', 'count'],
            'secondary_tokens': ['orders', 'conversions', 'purchases', 'revenue', 'sales', 'amount', 'checkout'],
            'category_tokens': ['funnel_stage', 'stage', 'step', 'event', 'status', 'channel', 'source', 'campaign', 'device'],
            'date_tokens': ['date', 'timestamp', 'day', 'week', 'month', 'order_date', 'session_date', 'time'],
            'panel_count': 6,
        },
    }

    config = presets.get(preset_key, presets['retail_sales'])

    metric = _pick_by_tokens(numeric_columns, config['metric_tokens'], default_metric)
    secondary_metric = _pick_by_tokens(numeric_columns, config['secondary_tokens'], default_secondary)
    if secondary_metric == metric:
        secondary_metric = next((col for col in numeric_columns if col != metric), secondary_metric)

    category = _pick_by_tokens(category_columns, config['category_tokens'], default_category)
    date_col = _pick_by_tokens(date_columns, config['date_tokens'], default_date)

    return {
        'metric': metric,
        'secondary_metric': secondary_metric,
        'category': category,
        'date': date_col,
        'panel_count': config['panel_count'],
    }


def _make_unique_column_names(columns):
    seen = {}
    output = []

    for raw_name in columns:
        base_name = str(raw_name).strip() or 'column'
        count = seen.get(base_name, 0)
        seen[base_name] = count + 1
        output.append(base_name if count == 0 else f"{base_name}_{count + 1}")

    return output


def _looks_like_market_matrix_upload(df: pd.DataFrame):
    """Detect CSV format where row 0 is ticker symbols and row 1 starts with Date."""
    if df.shape[0] < 3 or df.shape[1] < 3:
        return False

    first_cell = str(df.iloc[0, 0]).strip().lower()
    second_cell = str(df.iloc[1, 0]).strip().lower()
    if first_cell not in {'ticker', 'symbol', 'symbols'}:
        return False
    if second_cell not in {'date', 'datetime', 'time'}:
        return False

    tokens = [str(value).strip() for value in df.iloc[0, 1:].tolist()]
    valid = 0
    for token in tokens:
        if not token or token.lower() in {'nan', 'none'}:
            continue
        if re.fullmatch(r"[A-Z0-9\.-]{1,12}", token):
            valid += 1

    return valid >= max(2, int(len(tokens) * 0.35))


def _normalize_market_matrix_upload(df: pd.DataFrame):
    """Convert market matrix format into tidy numeric columns like Close_TSLA, Volume_TM, etc."""
    raw_columns = [str(col).strip() for col in df.columns.tolist()]
    ticker_row = [str(value).strip() for value in df.iloc[0].tolist()]
    date_label = str(df.iloc[1, 0]).strip() or 'Date'

    rebuilt_columns = [date_label]
    for index, raw_col in enumerate(raw_columns[1:], start=1):
        base_metric = re.sub(r"\.\d+$", "", raw_col).strip()
        ticker = ticker_row[index]
        if ticker and ticker.lower() not in {'nan', 'none'}:
            rebuilt_columns.append(f"{base_metric}_{ticker}")
        else:
            rebuilt_columns.append(base_metric)

    rebuilt_columns = _make_unique_column_names(rebuilt_columns)

    out = df.iloc[2:].copy().reset_index(drop=True)
    out.columns = rebuilt_columns

    date_col = rebuilt_columns[0]
    out[date_col] = pd.to_datetime(out[date_col], errors='coerce', format='mixed')

    numeric_cols = []
    for col in rebuilt_columns[1:]:
        cleaned = (
            out[col]
            .astype(str)
            .str.replace(',', '', regex=False)
            .str.replace('%', '', regex=False)
            .str.strip()
        )
        out[col] = pd.to_numeric(cleaned, errors='coerce')
        numeric_cols.append(col)

    out = out[out[date_col].notna()].copy()
    if numeric_cols:
        out = out.dropna(subset=numeric_cols, how='all')

    out = out.sort_values(date_col).reset_index(drop=True)
    return out


def _coerce_object_columns(df: pd.DataFrame):
    """Convert object columns to numeric/date when most values are parseable."""
    out = df.copy()
    object_cols = out.select_dtypes(include=['object']).columns.tolist()

    for col in object_cols:
        text = out[col].astype(str).str.strip()
        if text.empty:
            continue

        as_num = pd.to_numeric(
            text.str.replace(',', '', regex=False).str.replace('%', '', regex=False),
            errors='coerce',
        )
        if as_num.notna().mean() >= 0.85:
            out[col] = as_num
            continue

        as_date = pd.to_datetime(text, errors='coerce', format='mixed')
        if as_date.notna().mean() >= 0.9:
            out[col] = as_date

    return out


def _normalize_uploaded_dataframe(df: pd.DataFrame):
    out = df.copy()

    if _looks_like_market_matrix_upload(out):
        out = _normalize_market_matrix_upload(out)

    out = _coerce_object_columns(out)
    out.columns = _make_unique_column_names(out.columns)
    return out


def _load_json_dataset(file_path: str):
    try:
        return pd.read_json(file_path)
    except ValueError:
        # Support newline-delimited JSON (NDJSON)
        return pd.read_json(file_path, lines=True)


def _load_xml_dataset(file_path: str):
    return pd.read_xml(file_path)


def _load_txt_dataset(file_path: str):
    # Let pandas infer common delimiters (comma/tab/pipe/semicolon).
    try:
        return pd.read_csv(file_path, sep=None, engine='python')
    except Exception:
        return pd.read_csv(file_path, sep='\t')


def _load_sql_dataset(file_path: str):
    with open(file_path, 'r', encoding='utf-8', errors='replace') as handle:
        sql_text = handle.read()

    conn = sqlite3.connect(':memory:')
    try:
        conn.executescript(sql_text)
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if not table_rows:
            raise ValueError('SQL file did not create any readable tables.')

        first_table = table_rows[0][0]
        safe_table = str(first_table).replace('"', '""')
        return pd.read_sql_query(f'SELECT * FROM "{safe_table}"', conn)
    finally:
        conn.close()


def load_dataset(file_path: str = None, sample_name: str = 'iris'):
    """Load a dataset from a file path or seaborn sample dataset.
    Returns: (DataFrame, error_message_or_None)
    """
    try:
        if file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.csv':
                df = pd.read_csv(file_path)
            elif ext in ['.xls', '.xlsx']:
                df = pd.read_excel(file_path)
            elif ext == '.json':
                df = _load_json_dataset(file_path)
            elif ext in ['.xml', '.xlml']:
                df = _load_xml_dataset(file_path)
            elif ext == '.txt':
                df = _load_txt_dataset(file_path)
            elif ext == '.parquet':
                df = pd.read_parquet(file_path)
            elif ext == '.sql':
                df = _load_sql_dataset(file_path)
            else:
                return pd.DataFrame(), f"Unsupported file extension: {ext}"
            df = _normalize_uploaded_dataframe(df)
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


def get_analyst_brief(df: pd.DataFrame):
    """Return a concise analyst-grade brief for data quality and modeling readiness."""
    try:
        row_count, col_count = df.shape
        total_cells = row_count * col_count
        missing_cells = int(df.isna().sum().sum()) if total_cells else 0
        completeness = ((total_cells - missing_cells) / total_cells * 100.0) if total_cells else 100.0
        duplicate_rows = int(df.duplicated().sum()) if row_count else 0
        duplicate_pct = (duplicate_rows / row_count * 100.0) if row_count else 0.0
        memory_mb = float(df.memory_usage(deep=True).sum() / (1024 * 1024))

        numeric_cols = get_numeric_columns(df)
        categorical_cols = get_categorical_columns(df)
        date_cols = get_date_columns(df)

        snapshot_cards = [
            {'label': 'Rows', 'value': f"{row_count:,}", 'note': 'Records in analysis frame'},
            {'label': 'Columns', 'value': f"{col_count:,}", 'note': 'Features available'},
            {'label': 'Numeric Fields', 'value': f"{len(numeric_cols):,}", 'note': 'Eligible for KPI and correlation'},
            {'label': 'Data Completeness', 'value': f"{completeness:.1f}%", 'note': f"{missing_cells:,} missing cells"},
            {'label': 'Duplicate Rows', 'value': f"{duplicate_rows:,}", 'note': f"{duplicate_pct:.1f}% duplicate rate"},
            {'label': 'Est. In-Memory Size', 'value': f"{memory_mb:.2f} MB", 'note': 'Approximate DataFrame footprint'},
        ]

        quality_signals = []
        if completeness >= 98.0:
            quality_signals.append({
                'level': 'good',
                'title': 'Data completeness is strong',
                'detail': f"{completeness:.1f}% of cells are populated.",
            })
        elif completeness >= 92.0:
            quality_signals.append({
                'level': 'warn',
                'title': 'Moderate missing data detected',
                'detail': f"Missing rate is {100.0 - completeness:.1f}%. Prioritize imputation or filtering.",
            })
        else:
            quality_signals.append({
                'level': 'warn',
                'title': 'High missing-data risk',
                'detail': f"Missing rate is {100.0 - completeness:.1f}%. Model quality may degrade without cleanup.",
            })

        if duplicate_rows == 0:
            quality_signals.append({
                'level': 'good',
                'title': 'No duplicate records',
                'detail': 'Unique-row integrity looks healthy for trend and dashboard work.',
            })
        else:
            quality_signals.append({
                'level': 'warn',
                'title': 'Duplicate records found',
                'detail': f"{duplicate_rows:,} duplicate rows ({duplicate_pct:.1f}%) may bias totals.",
            })

        if len(date_cols) > 0:
            quality_signals.append({
                'level': 'good',
                'title': 'Time-series analysis ready',
                'detail': f"Detected time column(s): {', '.join(map(str, date_cols[:3]))}.",
            })
        else:
            quality_signals.append({
                'level': 'warn',
                'title': 'No clear time column',
                'detail': 'Add or map a date field to unlock trend and seasonality analysis.',
            })

        top_correlations = []
        if len(numeric_cols) >= 2:
            corr_df = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            corr_matrix = corr_df.corr(numeric_only=True)
            corr_candidates = []
            corr_columns = corr_matrix.columns.tolist()
            for i in range(len(corr_columns)):
                for j in range(i + 1, len(corr_columns)):
                    first = corr_columns[i]
                    second = corr_columns[j]
                    value = corr_matrix.loc[first, second]
                    if pd.isna(value):
                        continue
                    corr_candidates.append((abs(float(value)), float(value), str(first), str(second)))

            corr_candidates.sort(key=lambda item: item[0], reverse=True)
            for abs_value, value, first, second in corr_candidates[:5]:
                top_correlations.append({
                    'pair': f"{first} vs {second}",
                    'value': f"{value:.2f}",
                    'strength': 'strong' if abs_value >= 0.75 else ('moderate' if abs_value >= 0.4 else 'weak'),
                })

        outlier_summary = []
        if numeric_cols:
            for col in numeric_cols[:6]:
                series = pd.to_numeric(df[col], errors='coerce').dropna()
                if series.shape[0] < 8:
                    continue
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                if pd.isna(iqr) or iqr <= 0:
                    continue
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outlier_count = int(((series < lower) | (series > upper)).sum())
                if outlier_count <= 0:
                    continue
                pct = outlier_count / len(series) * 100.0
                outlier_summary.append({
                    'column': str(col),
                    'count': outlier_count,
                    'pct': f"{pct:.1f}%",
                })

        outlier_summary.sort(key=lambda item: item['count'], reverse=True)
        outlier_summary = outlier_summary[:5]

        recommendations = []
        if completeness < 95.0:
            recommendations.append('Build a missing-data treatment plan (drop, impute, or segment by completeness).')
        if duplicate_rows > 0:
            recommendations.append('Deduplicate before KPI aggregation to avoid inflated totals and conversion rates.')
        if top_correlations:
            strongest = top_correlations[0]
            recommendations.append(
                f"Review strongest relationship: {strongest['pair']} ({strongest['value']}) for driver analysis."
            )
        if len(date_cols) > 0 and len(numeric_cols) > 0:
            recommendations.append(
                f"Prioritize trend decomposition using {date_cols[0]} with your primary KPI for seasonality insights."
            )
        if not recommendations:
            recommendations.append('Dataset is structurally clean. Move to segmentation, forecasting, and scenario analysis.')

        return {
            'snapshot_cards': snapshot_cards,
            'quality_signals': quality_signals,
            'top_correlations': top_correlations,
            'outlier_summary': outlier_summary,
            'recommendations': recommendations,
        }
    except Exception as exc:
        return {
            'snapshot_cards': [],
            'quality_signals': [
                {
                    'level': 'warn',
                    'title': 'Analyst brief unavailable',
                    'detail': str(exc),
                }
            ],
            'top_correlations': [],
            'outlier_summary': [],
            'recommendations': ['Proceed with standard dashboard inspection.'],
        }


def get_metric_anomaly_alerts(df: pd.DataFrame, metric_col: str = None, date_col: str = None, max_alerts: int = 5):
    """Detect unusual spikes/drops in a metric over time and return compact alert records."""
    try:
        numeric_cols = get_numeric_columns(df)
        if not numeric_cols:
            return []

        if metric_col not in df.columns or metric_col not in numeric_cols:
            metric_col = numeric_cols[0]

        date_candidates = get_date_columns(df)
        if date_col not in df.columns:
            date_col = date_candidates[0] if date_candidates else None
        if not date_col:
            return []

        parsed_dates = pd.to_datetime(df[date_col], errors='coerce', format='mixed')
        metric_values = pd.to_numeric(df[metric_col], errors='coerce')
        ts_df = pd.DataFrame({'date': parsed_dates, 'metric': metric_values}).dropna()
        if ts_df.shape[0] < 8:
            return []

        daily = (
            ts_df.groupby(pd.Grouper(key='date', freq='D'))['metric']
            .sum()
            .dropna()
            .sort_index()
        )
        if daily.shape[0] < 8:
            return []

        baseline = daily.median()
        mad = (daily - baseline).abs().median()
        if pd.isna(mad) or mad <= 0:
            std = daily.std()
            if pd.isna(std) or std <= 0:
                return []
            score = (daily - baseline).abs() / std
        else:
            score = (daily - baseline).abs() / (1.4826 * mad)

        alerts_df = pd.DataFrame({'date': daily.index, 'value': daily.values, 'score': score.values})
        alerts_df = alerts_df[alerts_df['score'] >= 2.8].copy()

        if alerts_df.empty:
            return []

        alerts_df = alerts_df.sort_values('score', ascending=False).head(max_alerts)

        alerts = []
        for _, row in alerts_df.iterrows():
            direction = 'spike' if float(row['value']) >= float(baseline) else 'drop'
            alerts.append(
                {
                    'date': row['date'].strftime('%Y-%m-%d'),
                    'value': f"{row['value']:.2f}",
                    'score': f"{row['score']:.2f}",
                    'direction': direction,
                    'metric': str(metric_col),
                }
            )

        return alerts
    except Exception:
        return []


def get_chart_suggestions(df: pd.DataFrame, x_col: str = None, y_col: str = None, max_suggestions: int = 4):
    """Suggest chart types from selected columns and dataset structure."""
    suggestions = []
    all_cols = df.columns.tolist()
    numeric_cols = get_numeric_columns(df)
    date_cols = get_date_columns(df)

    x_is_numeric = x_col in numeric_cols
    y_is_numeric = y_col in numeric_cols
    x_is_date = x_col in date_cols
    y_is_date = y_col in date_cols

    default_x = x_col if x_col in numeric_cols else (numeric_cols[0] if numeric_cols else None)
    default_y = y_col if y_col in numeric_cols else (
        numeric_cols[1] if len(numeric_cols) > 1 else (numeric_cols[0] if numeric_cols else None)
    )

    def add(plot_type, reason, config=None):
        if plot_type in {item['plot_type'] for item in suggestions}:
            return
        suggestions.append({'plot_type': plot_type, 'reason': reason, 'config': config or {}})

    def config_for_2d(plot_type):
        return {
            'plot_family_select': '2d',
            'plot_type_select': plot_type,
            'plot_type_2d_select': plot_type,
            'x_col_select': default_x,
            'y_col_select': default_y,
        }

    if x_is_date and y_is_numeric:
        add('Line', f"{x_col} is temporal and {y_col} is numeric, ideal for trend analysis.", config_for_2d('Line'))

    if x_is_numeric and y_is_numeric:
        add('Scatter', f"{x_col} and {y_col} are numeric, suitable for relationship analysis.", config_for_2d('Scatter'))

    if x_col in all_cols and y_is_numeric and not x_is_numeric and not x_is_date:
        add('Bar', f"{x_col} is categorical and {y_col} is numeric, good for ranked comparisons.", config_for_2d('Bar'))

    if y_is_numeric or x_is_numeric:
        metric = y_col if y_is_numeric else x_col
        add('Histogram', f"{metric} is numeric, useful for distribution and skew checks.", config_for_2d('Histogram'))

    lat_col = next((c for c in numeric_cols if 'lat' in str(c).lower()), None)
    lon_col = next((c for c in numeric_cols if any(token in str(c).lower() for token in ['lon', 'lng', 'longitude'])), None)
    location_col = next((c for c in all_cols if any(token in str(c).lower() for token in ['country', 'state', 'region', 'city', 'location'])), None)

    if lat_col and lon_col:
        add(
            'Geo Scatter',
            f"Detected coordinate fields ({lat_col}, {lon_col}) for map plotting.",
            {
                'plot_family_select': 'geo',
                'plot_type_select': 'Geo Scatter',
                'plot_type_geo_select': 'Geo Scatter',
                'geo_lat_col_select': lat_col,
                'geo_lon_col_select': lon_col,
                'size_col_select': default_y,
                'plot_color_col_select': None,
            },
        )
    elif location_col and numeric_cols:
        add(
            'Geo Choropleth',
            f"Detected location field ({location_col}) and metrics for regional mapping.",
            {
                'plot_family_select': 'geo',
                'plot_type_select': 'Geo Choropleth',
                'plot_type_geo_select': 'Geo Choropleth',
                'geo_location_col_select': location_col,
                'size_col_select': default_y,
                'plot_color_col_select': None,
            },
        )

    if not suggestions:
        add('Bar', 'Start with categorical comparison; then switch to scatter when metric pairs are selected.', config_for_2d('Bar'))

    return suggestions[:max_suggestions]


def get_numeric_columns(df: pd.DataFrame):
    return df.select_dtypes(include=[np.number]).columns.tolist()


def get_categorical_columns(df: pd.DataFrame):
    return df.select_dtypes(include=['object', 'category', 'bool']).columns.tolist()


def get_date_columns(df: pd.DataFrame):
    """Detect likely date/time columns including parseable object columns."""
    candidates = []

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            candidates.append(col)

    object_cols = df.select_dtypes(include=['object']).columns.tolist()
    for col in object_cols:
        sample = df[col].dropna().head(300)
        if sample.empty:
            continue
        parsed = pd.to_datetime(sample, errors='coerce', format='mixed')
        if parsed.notna().mean() >= 0.7:
            candidates.append(col)

    # preserve order and remove duplicates
    return list(dict.fromkeys(candidates))


def get_dashboard_options(df: pd.DataFrame):
    """Return chart option lists and sensible defaults for business dashboards."""
    numeric_columns = get_numeric_columns(df)
    category_columns = get_categorical_columns(df)
    date_columns = get_date_columns(df)

    metric_preference = ('sales', 'revenue', 'profit', 'amount', 'price', 'cost', 'quantity', 'value')
    category_preference = ('store', 'branch', 'region', 'category', 'segment', 'department', 'city', 'country')
    date_preference = ('date', 'day', 'month', 'year', 'time')

    def _pick_preferred(columns, preferred_tokens):
        for token in preferred_tokens:
            for col in columns:
                if token in str(col).lower():
                    return col
        return columns[0] if columns else None

    default_metric = _pick_preferred(numeric_columns, metric_preference)
    default_secondary_metric = None
    if numeric_columns:
        default_secondary_metric = next((c for c in numeric_columns if c != default_metric), default_metric)
    default_category = _pick_preferred(category_columns, category_preference)
    default_date = _pick_preferred(date_columns, date_preference)

    return {
        'numeric_columns': numeric_columns,
        'category_columns': category_columns,
        'date_columns': date_columns,
        'default_metric': default_metric,
        'default_secondary_metric': default_secondary_metric,
        'default_category': default_category,
        'default_date': default_date,
    }


def get_dashboard_command_center(
    df: pd.DataFrame,
    metric_col: str = None,
    secondary_metric_col: str = None,
    category_col: str = None,
    date_col: str = None,
):
    """Return an executive dashboard summary for the Business Dashboard section."""
    try:
        if metric_col not in df.columns:
            return {
                'cards': [],
                'coverage_summary': 'Select a numeric KPI to unlock command-center insights.',
                'trend_summary': None,
                'top_category_summary': None,
            }

        metric_series = pd.to_numeric(df[metric_col], errors='coerce').dropna()
        if metric_series.empty:
            return {
                'cards': [],
                'coverage_summary': f"KPI '{metric_col}' has no usable numeric values.",
                'trend_summary': None,
                'top_category_summary': None,
            }

        row_count = int(metric_series.shape[0])
        metric_total = float(metric_series.sum())
        metric_avg = float(metric_series.mean())
        metric_median = float(metric_series.median())
        metric_p90 = float(metric_series.quantile(0.90))

        cards = [
            {
                'label': f"Total {metric_col}",
                'value': f"{metric_total:,.2f}",
                'note': 'Aggregate KPI value',
            },
            {
                'label': f"Average {metric_col}",
                'value': f"{metric_avg:,.2f}",
                'note': 'Mean per record',
            },
            {
                'label': f"Median {metric_col}",
                'value': f"{metric_median:,.2f}",
                'note': 'Robust midpoint',
            },
            {
                'label': f"P90 {metric_col}",
                'value': f"{metric_p90:,.2f}",
                'note': 'High-performance threshold',
            },
            {
                'label': 'Analyzed Rows',
                'value': f"{row_count:,}",
                'note': 'Rows with valid KPI values',
            },
        ]

        if secondary_metric_col and secondary_metric_col in df.columns and secondary_metric_col != metric_col:
            secondary_series = pd.to_numeric(df[secondary_metric_col], errors='coerce').dropna()
            if not secondary_series.empty:
                secondary_total = float(secondary_series.sum())
                cards.append(
                    {
                        'label': f"Total {secondary_metric_col}",
                        'value': f"{secondary_total:,.2f}",
                        'note': 'Secondary KPI aggregate',
                    }
                )

                if metric_total > 0:
                    ratio_pct = (secondary_total / metric_total) * 100.0
                    cards.append(
                        {
                            'label': f"{secondary_metric_col}/{metric_col}",
                            'value': f"{ratio_pct:.2f}%",
                            'note': 'Secondary-to-primary ratio',
                        }
                    )

        coverage_summary = f"Modeling on {row_count:,} valid rows for KPI '{metric_col}'."
        trend_summary = None
        top_category_summary = None

        if date_col and date_col in df.columns:
            parsed_dates = pd.to_datetime(df[date_col], errors='coerce', format='mixed')
            date_df = pd.DataFrame({'date': parsed_dates, 'metric': pd.to_numeric(df[metric_col], errors='coerce')}).dropna()
            if not date_df.empty:
                min_date = date_df['date'].min()
                max_date = date_df['date'].max()
                coverage_summary = (
                    f"Date coverage: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')} "
                    f"across {date_df.shape[0]:,} valid rows."
                )

                trend = (
                    date_df.groupby(pd.Grouper(key='date', freq='D'))['metric']
                    .sum()
                    .dropna()
                    .sort_index()
                )
                if trend.shape[0] >= 2 and float(trend.iloc[0]) != 0.0:
                    momentum_pct = ((float(trend.iloc[-1]) - float(trend.iloc[0])) / abs(float(trend.iloc[0]))) * 100.0
                    direction = 'upward' if momentum_pct >= 0 else 'downward'
                    trend_summary = (
                        f"Momentum is {direction}: {momentum_pct:+.2f}% from first to latest daily aggregate."
                    )

        if category_col and category_col in df.columns:
            category_df = df[[category_col, metric_col]].copy()
            category_df[metric_col] = pd.to_numeric(category_df[metric_col], errors='coerce')
            category_df[category_col] = category_df[category_col].astype(str)
            category_df = category_df.dropna(subset=[metric_col])
            if not category_df.empty:
                grouped = category_df.groupby(category_col, dropna=False)[metric_col].sum().sort_values(ascending=False)
                if not grouped.empty:
                    top_name = str(grouped.index[0])
                    top_value = float(grouped.iloc[0])
                    share_pct = (top_value / metric_total * 100.0) if metric_total > 0 else 0.0
                    top_category_summary = (
                        f"Top {category_col}: {top_name} with {top_value:,.2f} "
                        f"({share_pct:.2f}% of total {metric_col})."
                    )

        return {
            'cards': cards[:6],
            'coverage_summary': coverage_summary,
            'trend_summary': trend_summary,
            'top_category_summary': top_category_summary,
        }
    except Exception as exc:
        return {
            'cards': [],
            'coverage_summary': f"Dashboard command center unavailable: {exc}",
            'trend_summary': None,
            'top_category_summary': None,
        }


def _decode_plotly_typed_arrays(obj):
    """Convert Plotly v6 typed-array JSON objects into plain lists for broad JS compatibility."""
    if isinstance(obj, dict):
        if 'dtype' in obj and 'bdata' in obj:
            try:
                arr = np.frombuffer(base64.b64decode(obj['bdata']), dtype=np.dtype(obj['dtype']))
                shape = obj.get('shape')
                if shape:
                    if isinstance(shape, str):
                        dims = tuple(int(part) for part in shape.split(',') if part)
                    elif isinstance(shape, (list, tuple)):
                        dims = tuple(int(part) for part in shape)
                    else:
                        dims = ()
                    if dims:
                        arr = arr.reshape(dims)
                return arr.tolist()
            except Exception:
                return obj

        return {key: _decode_plotly_typed_arrays(value) for key, value in obj.items()}

    if isinstance(obj, list):
        return [_decode_plotly_typed_arrays(item) for item in obj]

    return obj


def _to_plotly_html(fig):
    fig.update_layout(template='plotly_white')

    if fig.layout.height is None:
        fig.update_layout(height=360)

    margin = fig.layout.margin
    if margin is None or all(getattr(margin, side, None) is None for side in ['l', 'r', 't', 'b']):
        fig.update_layout(margin=dict(l=35, r=20, t=55, b=35))

    # Plotly 6 can emit binary-encoded arrays (bdata). Convert them to plain lists
    # to keep charts rendering even with older Plotly.js bundles.
    figure_json = _decode_plotly_typed_arrays(fig.to_plotly_json())
    return pio.to_html(figure_json, full_html=False, include_plotlyjs=False)


def _funnel_stage_rank(stage_value):
    stage = str(stage_value).strip().lower()
    stage_rules = [
        (0, ['traffic', 'visit', 'session', 'impression', 'landing']),
        (1, ['view', 'browse', 'product', 'detail']),
        (2, ['cart', 'add_to_cart', 'add to cart', 'add']),
        (3, ['checkout', 'payment', 'billing']),
        (4, ['purchase', 'order', 'conversion', 'success', 'complete']),
    ]
    for rank, tokens in stage_rules:
        if any(token in stage for token in tokens):
            return rank
    return 100


def _detect_stage_column(df: pd.DataFrame, category_col: str = None):
    stage_tokens = ('stage', 'step', 'event', 'funnel', 'status')

    candidates = []
    if category_col and category_col in df.columns:
        candidates.append(category_col)

    for col in get_categorical_columns(df):
        col_name = str(col).lower()
        if any(token in col_name for token in stage_tokens):
            candidates.append(col)

    for col in candidates:
        if col not in df.columns:
            continue
        unique_count = df[col].astype(str).nunique(dropna=True)
        if 2 <= unique_count <= 25:
            return col

    return None


def get_funnel_stage_candidates(df: pd.DataFrame, category_col: str = None, max_items: int = 20):
    """Return likely stage labels and the detected stage column for funnel UI controls."""
    stage_col = _detect_stage_column(df, category_col)
    if not stage_col or stage_col not in df.columns:
        return [], None

    values = [
        str(v).strip()
        for v in df[stage_col].dropna().astype(str).tolist()
        if str(v).strip()
    ]
    if not values:
        return [], stage_col

    unique_values = list(dict.fromkeys(values))
    unique_values = sorted(unique_values, key=lambda item: (_funnel_stage_rank(item), item.lower()))
    return unique_values[:max_items], stage_col


def _parse_manual_stage_order(stage_order):
    if not stage_order:
        return []

    if isinstance(stage_order, (list, tuple)):
        raw_items = stage_order
    else:
        normalized = str(stage_order).replace('\n', ',')
        raw_items = normalized.split(',')

    cleaned = []
    seen = set()
    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        lowered = label.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(label)

    return cleaned


def _generate_ecommerce_funnel_panels(
    work_df: pd.DataFrame,
    metric_col: str,
    secondary_metric_col: str = None,
    category_col: str = None,
    date_col: str = None,
    stage_order=None,
):
    panels = []
    stage_col = _detect_stage_column(work_df, category_col)
    manual_order = _parse_manual_stage_order(stage_order)
    manual_order_map = {label.lower(): idx for idx, label in enumerate(manual_order)}

    if stage_col and stage_col in work_df.columns:
        stage_df = work_df[[stage_col, metric_col]].copy()
        stage_df[stage_col] = stage_df[stage_col].astype(str).replace({'nan': 'Unknown'})
        stage_agg = (
            stage_df.groupby(stage_col, dropna=False)[metric_col]
            .sum()
            .reset_index()
        )
        stage_agg['rank'] = stage_agg[stage_col].apply(_funnel_stage_rank)
        if manual_order_map:
            stage_agg['manual_rank'] = stage_agg[stage_col].str.lower().map(manual_order_map)
            stage_agg['manual_rank'] = stage_agg['manual_rank'].fillna(10_000)
            stage_agg = stage_agg.sort_values(['manual_rank', 'rank', metric_col], ascending=[True, True, False]).head(12)
        else:
            stage_agg = stage_agg.sort_values(['rank', metric_col], ascending=[True, False]).head(12)

        funnel_fig = go.Figure(go.Funnel(y=stage_agg[stage_col], x=stage_agg[metric_col]))
        panels.append({
            'title': f'Funnel Volume by {stage_col}',
            'html': _to_plotly_html(funnel_fig),
            'note': (
                'Manual stage order applied from input.'
                if manual_order_map else
                'Primary conversion path from traffic to purchase stages.'
            ),
        })

        stage_agg = stage_agg.reset_index(drop=True)
        stage_agg['prev_value'] = stage_agg[metric_col].shift(1)
        stage_agg['conversion_pct'] = np.where(
            stage_agg['prev_value'] > 0,
            (stage_agg[metric_col] / stage_agg['prev_value']) * 100.0,
            100.0,
        )
        stage_agg.loc[0, 'conversion_pct'] = 100.0

        conv_fig = px.bar(stage_agg, x=stage_col, y='conversion_pct')
        conv_fig.update_yaxes(title='Conversion %')
        panels.append({
            'title': f'Stage-to-Stage Conversion Rate ({metric_col})',
            'html': _to_plotly_html(conv_fig),
            'note': 'Higher values indicate stronger progression through funnel steps.',
        })

        stage_agg['dropoff_pct'] = 100.0 - stage_agg['conversion_pct']
        drop_fig = px.bar(stage_agg, x=stage_col, y='dropoff_pct')
        drop_fig.update_yaxes(title='Drop-off %')
        panels.append({
            'title': f'Stage Drop-off Rate ({metric_col})',
            'html': _to_plotly_html(drop_fig),
            'note': 'Highlights where users are dropping from the funnel.',
        })

        if secondary_metric_col and secondary_metric_col in work_df.columns:
            secondary_stage_df = work_df[[stage_col, secondary_metric_col]].copy()
            secondary_stage_df[secondary_metric_col] = pd.to_numeric(
                secondary_stage_df[secondary_metric_col],
                errors='coerce',
            )
            secondary_stage_df = secondary_stage_df.dropna()
            if not secondary_stage_df.empty:
                sec_agg = (
                    secondary_stage_df.groupby(stage_col, dropna=False)[secondary_metric_col]
                    .sum()
                    .reset_index()
                )
                sec_agg['rank'] = sec_agg[stage_col].apply(_funnel_stage_rank)
                sec_agg = sec_agg.sort_values(['rank', secondary_metric_col], ascending=[True, False]).head(12)

                sec_fig = px.bar(sec_agg, x=stage_col, y=secondary_metric_col)
                panels.append({
                    'title': f'{secondary_metric_col} by Funnel Stage',
                    'html': _to_plotly_html(sec_fig),
                    'note': 'Monetization or outcome signal at each funnel stage.',
                })

    if category_col and category_col in work_df.columns and secondary_metric_col and secondary_metric_col in work_df.columns:
        ratio_df = work_df[[category_col, metric_col, secondary_metric_col]].copy()
        ratio_df[secondary_metric_col] = pd.to_numeric(ratio_df[secondary_metric_col], errors='coerce')
        ratio_df = ratio_df.dropna().copy()
        if not ratio_df.empty:
            grouped = ratio_df.groupby(category_col, dropna=False)[[metric_col, secondary_metric_col]].sum()
            grouped = grouped[grouped[metric_col] > 0]
            if not grouped.empty:
                grouped['conversion_pct'] = (grouped[secondary_metric_col] / grouped[metric_col]) * 100.0
                grouped = grouped.sort_values('conversion_pct', ascending=False).head(12).reset_index()

                ratio_fig = px.bar(grouped, x=category_col, y='conversion_pct')
                ratio_fig.update_yaxes(title='Conversion %')
                panels.append({
                    'title': f'Conversion % by {category_col}',
                    'html': _to_plotly_html(ratio_fig),
                    'note': f'Computed as {secondary_metric_col} / {metric_col}.',
                })

    if date_col and date_col in work_df.columns:
        parsed_dates = pd.to_datetime(work_df[date_col], errors='coerce', format='mixed')
        time_df = pd.DataFrame({
            'date': parsed_dates,
            metric_col: work_df[metric_col],
        }).dropna()
        if not time_df.empty:
            trend = (
                time_df.groupby(pd.Grouper(key='date', freq='D'))[metric_col]
                .sum()
                .reset_index()
                .dropna()
                .tail(365)
            )
            trend_fig = px.line(trend, x='date', y=metric_col, markers=True)
            panels.append({
                'title': f'Funnel Traffic Trend ({metric_col})',
                'html': _to_plotly_html(trend_fig),
                'note': 'Daily trend to track demand and campaign impact.',
            })

    return panels


def generate_dashboard_panels(
    df: pd.DataFrame,
    metric_col: str,
    secondary_metric_col: str = None,
    category_col: str = None,
    date_col: str = None,
    panel_count: int = 6,
    preset_key: str = None,
    stage_order=None,
):
    """Generate 4 or 6 business dashboard panels using Plotly HTML snippets."""
    panels = []
    requested_count = 6 if panel_count not in [4, 6] else panel_count

    if metric_col not in df.columns:
        return panels

    work_df = df.copy()
    work_df[metric_col] = pd.to_numeric(work_df[metric_col], errors='coerce')
    work_df = work_df.dropna(subset=[metric_col])
    if work_df.empty:
        return panels

    if secondary_metric_col and secondary_metric_col in work_df.columns:
        work_df[secondary_metric_col] = pd.to_numeric(work_df[secondary_metric_col], errors='coerce')

    if preset_key == 'ecommerce_funnel':
        funnel_panels = _generate_ecommerce_funnel_panels(
            work_df,
            metric_col=metric_col,
            secondary_metric_col=secondary_metric_col,
            category_col=category_col,
            date_col=date_col,
            stage_order=stage_order,
        )
        panels.extend(funnel_panels)
        if len(panels) >= requested_count:
            return panels[:requested_count]

    # 1) Trend chart (date-based if possible, otherwise record index trend)
    trend_series = work_df[metric_col]
    if date_col and date_col in work_df.columns:
        parsed_dates = pd.to_datetime(work_df[date_col], errors='coerce')
        trend_df = pd.DataFrame({'metric': trend_series, 'date': parsed_dates}).dropna()
        if trend_df.shape[0] >= 3:
            trend_agg = (
                trend_df.groupby(pd.Grouper(key='date', freq='D'))['metric']
                .sum()
                .reset_index()
                .dropna()
                .tail(365)
            )
            fig = px.line(trend_agg, x='date', y='metric', markers=True)
            fig.update_traces(line=dict(width=2))
            panels.append({
                'title': f'{metric_col} Trend Over Time',
                'html': _to_plotly_html(fig),
                'note': f'Aggregated daily from {date_col}.',
            })
        else:
            date_col = None

    if not date_col:
        trend_df = work_df[[metric_col]].head(1500).reset_index(drop=True)
        trend_df['record'] = trend_df.index + 1
        fig = px.line(trend_df, x='record', y=metric_col, markers=False)
        panels.append({
            'title': f'{metric_col} Trend by Record Order',
            'html': _to_plotly_html(fig),
            'note': 'Useful when no date/time column is available.',
        })

    # 2) Distribution chart
    fig = px.histogram(work_df, x=metric_col, nbins=40)
    panels.append({
        'title': f'{metric_col} Distribution',
        'html': _to_plotly_html(fig),
        'note': 'Shows concentration and outliers in the selected KPI.',
    })

    # 3) Category contribution bar chart
    if category_col and category_col in work_df.columns:
        cat_df = work_df[[category_col, metric_col]].copy()
        cat_df[category_col] = cat_df[category_col].astype(str).replace({'nan': 'Unknown'})
        grouped = (
            cat_df.groupby(category_col, dropna=False)[metric_col]
            .sum()
            .sort_values(ascending=False)
        )
        top_grouped = grouped.head(12).reset_index()
        fig = px.bar(top_grouped, x=category_col, y=metric_col)
        panels.append({
            'title': f'Top {category_col} by {metric_col}',
            'html': _to_plotly_html(fig),
            'note': 'Best categories, stores, or business units by KPI.',
        })

        # 4) Category share donut chart
        donut_series = grouped.head(6)
        others_sum = grouped.iloc[6:].sum()
        if others_sum > 0:
            donut_series.loc['Others'] = others_sum
        donut_df = donut_series.reset_index()
        donut_df.columns = [category_col, metric_col]
        fig = px.pie(donut_df, names=category_col, values=metric_col, hole=0.5)
        panels.append({
            'title': f'{category_col} Share of {metric_col}',
            'html': _to_plotly_html(fig),
            'note': 'Quick mix view to identify concentration risk.',
        })

        # 5) Box chart by category
        box_df = cat_df.head(5000)
        fig = px.box(box_df, x=category_col, y=metric_col, points='outliers')
        panels.append({
            'title': f'{metric_col} Spread by {category_col}',
            'html': _to_plotly_html(fig),
            'note': 'Compares median and spread across business segments.',
        })
    else:
        # fallback category-independent panels
        fig = px.box(work_df, y=metric_col, points='outliers')
        panels.append({
            'title': f'{metric_col} Box Plot',
            'html': _to_plotly_html(fig),
            'note': 'Fallback spread chart when no category column exists.',
        })

        try:
            bucketed = pd.qcut(work_df[metric_col], q=5, duplicates='drop')
            bucket_counts = bucketed.value_counts().sort_index()
            bucket_df = bucket_counts.reset_index()
            bucket_df.columns = ['Bucket', 'Count']
            bucket_df['Bucket'] = bucket_df['Bucket'].astype(str)
            fig = px.bar(bucket_df, x='Bucket', y='Count')
        except Exception:
            fallback_counts = work_df[metric_col].round(2).value_counts().head(10)
            bucket_df = fallback_counts.reset_index()
            bucket_df.columns = ['Value', 'Count']
            fig = px.bar(bucket_df, x='Value', y='Count')
        panels.append({
            'title': f'{metric_col} Quantile Buckets',
            'html': _to_plotly_html(fig),
            'note': 'Distribution fallback for datasets without categories.',
        })

    # 6) Cross-metric relationship chart
    if secondary_metric_col and secondary_metric_col in work_df.columns and secondary_metric_col != metric_col:
        scatter_df = work_df[[metric_col, secondary_metric_col]].copy()
        scatter_df[secondary_metric_col] = pd.to_numeric(scatter_df[secondary_metric_col], errors='coerce')
        scatter_df = scatter_df.dropna().head(4000)
        if not scatter_df.empty:
            fig = px.scatter(scatter_df, x=metric_col, y=secondary_metric_col)
            panels.append({
                'title': f'{metric_col} vs {secondary_metric_col}',
                'html': _to_plotly_html(fig),
                'note': 'Shows relationship between primary and secondary KPIs.',
            })

    if len(panels) < 6:
        numeric_cols = get_numeric_columns(work_df)[:8]
        if len(numeric_cols) >= 2:
            corr = work_df[numeric_cols].corr()
            heatmap = go.Figure(
                data=go.Heatmap(
                    z=corr.values,
                    x=corr.columns.tolist(),
                    y=corr.index.tolist(),
                    colorscale='RdBu',
                    zmid=0,
                )
            )
            panels.append({
                'title': 'Correlation Matrix (Top Numeric Columns)',
                'html': _to_plotly_html(heatmap),
                'note': 'Detects variables that move together.',
            })

    return panels[:requested_count]


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
        html = _to_plotly_html(fig)
        return html, None
    except Exception as e:
        return None, str(e)


def generate_advanced_plotly_plot(
    df: pd.DataFrame,
    plot_type: str,
    x_col: str = None,
    y_col: str = None,
    z_col: str = None,
    color_col: str = None,
    size_col: str = None,
    lat_col: str = None,
    lon_col: str = None,
    location_col: str = None,
    geo_scope: str = 'world',
    geo_map_style: str = 'carto-positron',
    geo_projection: str = 'natural earth',
    geo_location_mode: str = 'country names',
    geo_choropleth_color_scale: str = 'Blues',
    animation_col: str = None,
):
    """Generate advanced 3D and geographic Plotly visualizations as HTML snippets."""
    try:
        advanced_types = {'3D Scatter', '3D Surface', 'Geo Scatter', 'Geo Density', 'Geo Choropleth'}
        if plot_type not in advanced_types:
            return None, f'Unsupported advanced plot type: {plot_type}'

        safe_scope = geo_scope if geo_scope in {
            'world', 'usa', 'europe', 'asia', 'africa', 'north america', 'south america'
        } else 'world'
        safe_projection = geo_projection if geo_projection in {
            'natural earth', 'equirectangular', 'mercator', 'orthographic', 'robinson'
        } else 'natural earth'
        safe_map_style = geo_map_style if geo_map_style in {
            'open-street-map', 'carto-positron', 'carto-darkmatter', 'stamen-terrain', 'stamen-toner'
        } else 'carto-positron'
        safe_location_mode = geo_location_mode if geo_location_mode in {
            'country names',
            'ISO-3',
            'USA-states',
        } else 'country names'
        safe_choropleth_scale = geo_choropleth_color_scale if geo_choropleth_color_scale in {
            'Blues',
            'Viridis',
            'YlOrRd',
            'Plasma',
        } else 'Blues'

        def _infer_location_mode(location_series, preferred_mode):
            if preferred_mode != 'country names':
                return preferred_mode

            sample = [str(v).strip() for v in location_series.dropna().tolist() if str(v).strip()]
            if not sample:
                return preferred_mode

            iso3_like = sum(1 for value in sample if re.fullmatch(r'[A-Z]{3}', value))
            if iso3_like / len(sample) >= 0.65:
                return 'ISO-3'

            return preferred_mode

        def _build_discrete_colors(scale_name):
            scale_map = {
                'Blues': px.colors.sequential.Blues,
                'Viridis': px.colors.sequential.Viridis,
                'YlOrRd': px.colors.sequential.YlOrRd,
                'Plasma': px.colors.sequential.Plasma,
            }
            base = scale_map.get(scale_name, px.colors.sequential.Blues)
            # Skip very faint first stop for better country distinction.
            return base[1:] if len(base) > 2 else base

        def _normalize_animation_frame(series):
            as_numeric = pd.to_numeric(series, errors='coerce')
            if as_numeric.notna().mean() >= 0.7:
                rounded = as_numeric.round()
                if rounded.dropna().between(1800, 2200).mean() >= 0.7:
                    frame = rounded.astype('Int64').astype(str)
                    return frame.where(rounded.notna(), np.nan)

            parsed_dates = pd.to_datetime(series, errors='coerce', format='mixed')
            if parsed_dates.notna().mean() >= 0.6:
                years = parsed_dates.dt.year
                frame = years.astype('Int64').astype(str)
                return frame.where(years.notna(), np.nan)

            frame = series.astype(str).str.strip()
            return frame.replace({'': np.nan, 'nan': np.nan, 'None': np.nan, 'NaT': np.nan})

        def _append_year_trend_html(map_fig, trend_df, frame_col, metric_col=None):
            map_html = _to_plotly_html(map_fig)

            if frame_col not in trend_df.columns:
                return map_html

            work = trend_df[[frame_col]].copy()
            if metric_col and metric_col in trend_df.columns:
                work[metric_col] = pd.to_numeric(trend_df[metric_col], errors='coerce')
                work = work.dropna(subset=[frame_col, metric_col])
            else:
                work = work.dropna(subset=[frame_col])

            if work.empty:
                return map_html

            if metric_col and metric_col in work.columns:
                summary = work.groupby(frame_col, dropna=False)[metric_col].sum().reset_index()
                y_col = metric_col
                line_title = f'Year-wise Performance ({metric_col})'
            else:
                summary = work.groupby(frame_col, dropna=False).size().reset_index(name='Record Count')
                y_col = 'Record Count'
                line_title = 'Year-wise Record Count'

            if summary.shape[0] < 2:
                return map_html

            numeric_sort = pd.to_numeric(summary[frame_col], errors='coerce')
            if numeric_sort.notna().sum() == summary.shape[0]:
                summary = summary.assign(_sort=numeric_sort).sort_values('_sort').drop(columns=['_sort'])
            else:
                summary = summary.sort_values(frame_col)

            trend_fig = px.line(summary, x=frame_col, y=y_col, markers=True)
            trend_fig.update_layout(
                title=line_title,
                height=320,
                margin=dict(l=35, r=20, t=55, b=35),
            )

            return map_html + '<div class="mt-3">' + _to_plotly_html(trend_fig) + '</div>'

        if plot_type in {'3D Scatter', '3D Surface'}:
            required = [x_col, y_col, z_col]
            if not all(col and col in df.columns for col in required):
                return None, '3D plots require valid X, Y, and Z numeric columns.'

            work_df = df[[x_col, y_col, z_col]].copy()
            work_df[x_col] = pd.to_numeric(work_df[x_col], errors='coerce')
            work_df[y_col] = pd.to_numeric(work_df[y_col], errors='coerce')
            work_df[z_col] = pd.to_numeric(work_df[z_col], errors='coerce')

            size_is_valid = bool(size_col and size_col in df.columns)
            if size_is_valid:
                work_df[size_col] = pd.to_numeric(df[size_col], errors='coerce')

            color_is_valid = bool(color_col and color_col in df.columns)
            if color_is_valid:
                work_df[color_col] = df[color_col].astype(str)

            drop_cols = [x_col, y_col, z_col] + ([size_col] if size_is_valid else [])
            work_df = work_df.dropna(subset=drop_cols).head(20000)
            if work_df.empty:
                return None, 'No valid rows remain for the selected 3D options.'

            if plot_type == '3D Scatter':
                scatter_kwargs = {
                    'x': x_col,
                    'y': y_col,
                    'z': z_col,
                    'opacity': 0.82,
                }
                if color_is_valid:
                    scatter_kwargs['color'] = color_col
                if size_is_valid:
                    work_df[size_col] = work_df[size_col].clip(lower=0)
                    scatter_kwargs['size'] = size_col
                    scatter_kwargs['size_max'] = 22

                fig = px.scatter_3d(work_df, **scatter_kwargs)
                fig.update_layout(
                    title=f'3D Scatter: {z_col} vs {x_col} and {y_col}',
                    scene=dict(
                        xaxis_title=x_col,
                        yaxis_title=y_col,
                        zaxis_title=z_col,
                    ),
                )
                return _to_plotly_html(fig), None

            # 3D Surface
            surface_df = work_df[[x_col, y_col, z_col]].copy()
            if surface_df.shape[0] < 20:
                return None, '3D surface needs more data points (at least 20 valid rows).'

            bin_count = max(6, min(24, int(np.sqrt(surface_df.shape[0]) / 2)))
            surface_df['_x_bin'] = pd.cut(surface_df[x_col], bins=bin_count, labels=False, duplicates='drop')
            surface_df['_y_bin'] = pd.cut(surface_df[y_col], bins=bin_count, labels=False, duplicates='drop')
            surface_df = surface_df.dropna(subset=['_x_bin', '_y_bin'])
            surface_df['_x_bin'] = surface_df['_x_bin'].astype(int)
            surface_df['_y_bin'] = surface_df['_y_bin'].astype(int)

            grouped = surface_df.groupby(['_y_bin', '_x_bin'])[z_col].mean().reset_index()
            if grouped.empty:
                return None, 'Could not build a valid grid for the 3D surface plot.'

            pivot = grouped.pivot(index='_y_bin', columns='_x_bin', values=z_col).sort_index().sort_index(axis=1)
            if pivot.shape[0] < 2 or pivot.shape[1] < 2:
                return None, '3D surface requires a richer spread across X and Y values.'

            x_axis = surface_df.groupby('_x_bin')[x_col].mean().reindex(pivot.columns).values
            y_axis = surface_df.groupby('_y_bin')[y_col].mean().reindex(pivot.index).values
            fig = go.Figure(data=[
                go.Surface(
                    z=pivot.values,
                    x=x_axis,
                    y=y_axis,
                    colorscale='Viridis',
                    colorbar=dict(title=z_col),
                )
            ])
            fig.update_layout(
                title=f'3D Surface: {z_col} over {x_col} and {y_col}',
                scene=dict(
                    xaxis_title=x_col,
                    yaxis_title=y_col,
                    zaxis_title=z_col,
                ),
            )
            return _to_plotly_html(fig), None

        # Geographic plots
        has_lat_lon = bool(lat_col and lon_col and lat_col in df.columns and lon_col in df.columns)
        has_location = bool(location_col and location_col in df.columns)
        if not has_lat_lon and not has_location:
            return None, 'Geo plots require latitude/longitude columns or a location name column.'

        effective_location_mode = safe_location_mode
        if has_location:
            effective_location_mode = _infer_location_mode(df[location_col], safe_location_mode)

        color_is_valid = bool(color_col and color_col in df.columns)
        size_is_valid = bool(size_col and size_col in df.columns)
        animation_is_valid = bool(animation_col and animation_col in df.columns)

        if plot_type == 'Geo Scatter':
            if has_lat_lon:
                geo_df = df[[lat_col, lon_col]].copy()
                geo_df[lat_col] = pd.to_numeric(geo_df[lat_col], errors='coerce')
                geo_df[lon_col] = pd.to_numeric(geo_df[lon_col], errors='coerce')
                if color_is_valid:
                    geo_df[color_col] = df[color_col]
                if size_is_valid:
                    geo_df[size_col] = pd.to_numeric(df[size_col], errors='coerce')
                if has_location:
                    geo_df[location_col] = df[location_col].astype(str)
                if animation_is_valid:
                    geo_df['_animation_frame'] = _normalize_animation_frame(df[animation_col])

                drop_cols = [lat_col, lon_col] + ([size_col] if size_is_valid else [])
                if animation_is_valid:
                    drop_cols.append('_animation_frame')
                geo_df = geo_df.dropna(subset=drop_cols)
                geo_df = geo_df[(geo_df[lat_col].between(-90, 90)) & (geo_df[lon_col].between(-180, 180))].head(10000)
                if geo_df.empty:
                    return None, 'No valid geographic coordinate rows for the selected options.'

                try:
                    map_kwargs = {
                        'lat': lat_col,
                        'lon': lon_col,
                        'mapbox_style': safe_map_style,
                        'zoom': 1.2,
                        'height': 460,
                    }
                    if color_is_valid:
                        map_kwargs['color'] = color_col
                    if size_is_valid:
                        geo_df[size_col] = geo_df[size_col].clip(lower=0)
                        map_kwargs['size'] = size_col
                    if has_location:
                        map_kwargs['hover_name'] = location_col
                    if animation_is_valid:
                        map_kwargs['animation_frame'] = '_animation_frame'

                    center = {
                        'lat': float(geo_df[lat_col].mean()),
                        'lon': float(geo_df[lon_col].mean()),
                    }
                    fig = px.scatter_mapbox(geo_df, center=center, **map_kwargs)
                    fig.update_layout(margin=dict(l=20, r=20, t=55, b=20))
                    if animation_is_valid:
                        metric_for_trend = size_col if size_is_valid else None
                        return _append_year_trend_html(fig, geo_df, '_animation_frame', metric_for_trend), None

                    return _to_plotly_html(fig), None
                except Exception:
                    scatter_kwargs = {
                        'lat': lat_col,
                        'lon': lon_col,
                        'projection': safe_projection,
                    }
                    if color_is_valid:
                        scatter_kwargs['color'] = color_col
                    if size_is_valid:
                        geo_df[size_col] = geo_df[size_col].clip(lower=0)
                        scatter_kwargs['size'] = size_col
                    if has_location:
                        scatter_kwargs['hover_name'] = location_col
                    if animation_is_valid:
                        scatter_kwargs['animation_frame'] = '_animation_frame'

                    fig = px.scatter_geo(geo_df, **scatter_kwargs)
                    fig.update_geos(scope=safe_scope, showcountries=True, showland=True)
                    if animation_is_valid:
                        metric_for_trend = size_col if size_is_valid else None
                        return _append_year_trend_html(fig, geo_df, '_animation_frame', metric_for_trend), None

                    return _to_plotly_html(fig), None

            # Location-based scatter (e.g., country names)
            loc_df = df[[location_col]].dropna().copy()
            loc_df[location_col] = loc_df[location_col].astype(str)
            if color_is_valid:
                loc_df[color_col] = df[color_col]
            if size_is_valid:
                loc_df[size_col] = pd.to_numeric(df[size_col], errors='coerce')
                loc_df = loc_df.dropna(subset=[size_col])
            if animation_is_valid:
                loc_df['_animation_frame'] = _normalize_animation_frame(df[animation_col])
                loc_df = loc_df.dropna(subset=['_animation_frame'])

            if loc_df.empty:
                return None, 'No valid location rows for geo scatter plot.'

            scatter_kwargs = {
                'locations': location_col,
                'locationmode': effective_location_mode,
                'projection': safe_projection,
            }
            if color_is_valid:
                scatter_kwargs['color'] = color_col
            if size_is_valid:
                loc_df[size_col] = loc_df[size_col].clip(lower=0)
                scatter_kwargs['size'] = size_col
            if animation_is_valid:
                scatter_kwargs['animation_frame'] = '_animation_frame'

            fig = px.scatter_geo(loc_df.head(5000), **scatter_kwargs)
            scatter_scope = 'usa' if effective_location_mode == 'USA-states' else safe_scope
            fig.update_geos(scope=scatter_scope, showcountries=True, showland=True)
            if animation_is_valid:
                metric_for_trend = size_col if size_is_valid else None
                return _append_year_trend_html(fig, loc_df, '_animation_frame', metric_for_trend), None

            return _to_plotly_html(fig), None

        if plot_type == 'Geo Choropleth':
            if not has_location:
                return None, 'Geo choropleth requires a location name/code column.'

            value_col = None
            for candidate in [size_col, x_col, y_col, z_col]:
                if candidate and candidate in df.columns:
                    value_col = candidate
                    break

            choropleth_df = df[[location_col]].copy()
            choropleth_df[location_col] = choropleth_df[location_col].astype(str)
            choropleth_df = choropleth_df[choropleth_df[location_col].str.strip() != '']
            if animation_is_valid:
                choropleth_df['_animation_frame'] = _normalize_animation_frame(df[animation_col])
                choropleth_df = choropleth_df.dropna(subset=['_animation_frame'])

            if value_col:
                choropleth_df[value_col] = pd.to_numeric(df[value_col], errors='coerce')
                choropleth_df = choropleth_df.dropna(subset=[value_col])
                if choropleth_df.empty:
                    return None, 'No valid value rows for geo choropleth.'

                group_cols = [location_col]
                if animation_is_valid:
                    group_cols.insert(0, '_animation_frame')
                agg_df = (
                    choropleth_df.groupby(group_cols, dropna=False)[value_col]
                    .sum()
                    .reset_index()
                )
                color_column = value_col
            else:
                group_cols = [location_col]
                if animation_is_valid:
                    group_cols.insert(0, '_animation_frame')
                agg_df = (
                    choropleth_df.groupby(group_cols, dropna=False)
                    .size()
                    .reset_index(name='count')
                )
                color_column = 'count'

            if agg_df.empty:
                return None, 'No valid rows available for geo choropleth.'

            choropleth_scope = 'usa' if effective_location_mode == 'USA-states' else safe_scope
            choropleth_kwargs = {
                'locations': location_col,
                'locationmode': effective_location_mode,
                'color': color_column,
                'scope': choropleth_scope,
                'projection': safe_projection,
            }
            if animation_is_valid:
                choropleth_kwargs['animation_frame'] = '_animation_frame'

            if value_col:
                choropleth_kwargs['color_continuous_scale'] = safe_choropleth_scale
            else:
                # Without a metric, color each country/category distinctly.
                choropleth_kwargs['color_discrete_sequence'] = _build_discrete_colors(safe_choropleth_scale)

            fig = px.choropleth(agg_df.head(5000), **choropleth_kwargs)
            fig.update_geos(showcountries=True, showland=True)
            fig.update_layout(margin=dict(l=20, r=20, t=55, b=20), height=460)
            if animation_is_valid:
                metric_for_trend = color_column if color_column in agg_df.columns else None
                return _append_year_trend_html(fig, agg_df, '_animation_frame', metric_for_trend), None

            return _to_plotly_html(fig), None

        # Geo Density
        if not has_lat_lon:
            return None, 'Geo density requires latitude and longitude columns.'

        geo_df = df[[lat_col, lon_col]].copy()
        geo_df[lat_col] = pd.to_numeric(geo_df[lat_col], errors='coerce')
        geo_df[lon_col] = pd.to_numeric(geo_df[lon_col], errors='coerce')
        if animation_is_valid:
            geo_df['_animation_frame'] = _normalize_animation_frame(df[animation_col])
        geo_df = geo_df.dropna(subset=[lat_col, lon_col])
        geo_df = geo_df[(geo_df[lat_col].between(-90, 90)) & (geo_df[lon_col].between(-180, 180))].head(30000)
        if geo_df.empty:
            return None, 'No valid coordinate rows for geo density plot.'

        z_column = None
        if size_is_valid:
            geo_df[size_col] = pd.to_numeric(df[size_col], errors='coerce')
            geo_df = geo_df.dropna(subset=[size_col])
            geo_df[size_col] = geo_df[size_col].clip(lower=0)
            z_column = size_col

        if animation_is_valid:
            geo_df = geo_df.dropna(subset=['_animation_frame'])
            if geo_df.empty:
                return None, 'No valid year/time rows for geo animation.'

        if not z_column:
            geo_df['_density_weight'] = 1
            z_column = '_density_weight'

        center = {
            'lat': float(geo_df[lat_col].mean()),
            'lon': float(geo_df[lon_col].mean()),
        }
        fig = px.density_mapbox(
            geo_df,
            lat=lat_col,
            lon=lon_col,
            z=z_column,
            radius=20,
            center=center,
            zoom=1.1,
            mapbox_style=safe_map_style,
            height=460,
            animation_frame='_animation_frame' if animation_is_valid else None,
        )
        fig.update_layout(margin=dict(l=20, r=20, t=55, b=20))
        if animation_is_valid:
            metric_for_trend = size_col if size_is_valid else None
            return _append_year_trend_html(fig, geo_df, '_animation_frame', metric_for_trend), None

        return _to_plotly_html(fig), None

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
