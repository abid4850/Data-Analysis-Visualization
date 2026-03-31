from pathlib import Path
import logging
import os
import time
import textwrap

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.files.storage import FileSystemStorage
from django.db import connection
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from . import data_processor
from blog.models import Blog
from .forms import NewsletterSubscriptionForm
from .models import DatasetTag, NewsletterSubscriber, StoredDataset

logger = logging.getLogger("dataviz")

CSV_UPLOAD_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
}
TEXT_UPLOAD_CONTENT_TYPES = {
    "text/plain",
}
JSON_UPLOAD_CONTENT_TYPES = {
    "application/json",
    "text/json",
    "application/x-ndjson",
}
XML_UPLOAD_CONTENT_TYPES = {
    "application/xml",
    "text/xml",
}
XLSX_UPLOAD_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}
XLS_UPLOAD_CONTENT_TYPES = {
    "application/vnd.ms-excel",
    "application/octet-stream",
}
PARQUET_UPLOAD_CONTENT_TYPES = {
    "application/octet-stream",
    "application/parquet",
    "application/x-parquet",
}


def _remaining_time_seconds(start_time):
    return settings.ANALYSIS_TIMEOUT_SECONDS - (time.monotonic() - start_time)


def _parse_stage_order_input(raw_text):
    if not raw_text:
        return []

    normalized = str(raw_text).replace('\n', ',')
    values = [item.strip() for item in normalized.split(',') if item.strip()]

    unique_values = []
    seen = set()
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_values.append(value)

    return unique_values


def _pick_column_by_tokens(columns, tokens):
    lowered = [(col, str(col).lower()) for col in columns]
    for token in tokens:
        for original, lowered_name in lowered:
            if token in lowered_name:
                return original
    return None


def _get_stage_order_map(session):
    data = session.get('dashboard_stage_order_by_preset', {})
    if isinstance(data, dict):
        return {str(key): str(value) for key, value in data.items()}
    return {}


def _parse_dataset_tags(raw_text, max_tags=12):
    if not raw_text:
        return []

    cleaned = str(raw_text).replace('\n', ',')
    chunks = [chunk.strip() for chunk in cleaned.split(',') if chunk.strip()]

    unique_tags = []
    seen = set()
    for chunk in chunks:
        normalized = ' '.join(chunk.split())
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_tags.append(normalized[:60])
        if len(unique_tags) >= max_tags:
            break

    return unique_tags


def _validate_uploaded_file(uploaded_file):
    max_upload_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if uploaded_file.size > max_upload_bytes:
        return False, f"File is too large. Max allowed size is {settings.MAX_UPLOAD_SIZE_MB} MB."

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        return False, (
            "Unsupported file type. Allowed formats: "
            ".csv, .xls, .xlsx, .json, .xml, .xlml, .txt, .parquet, .sql."
        )

    content_type = (uploaded_file.content_type or "").lower()
    if extension == ".csv" and content_type and content_type not in CSV_UPLOAD_CONTENT_TYPES.union(TEXT_UPLOAD_CONTENT_TYPES):
        return False, "File content type does not match CSV upload requirements."
    if extension == ".xls" and content_type and content_type not in XLS_UPLOAD_CONTENT_TYPES:
        return False, "File content type does not match XLS upload requirements."
    if extension == ".xlsx" and content_type and content_type not in XLSX_UPLOAD_CONTENT_TYPES:
        return False, "File content type does not match XLSX upload requirements."
    if extension == ".json" and content_type and content_type not in JSON_UPLOAD_CONTENT_TYPES.union(TEXT_UPLOAD_CONTENT_TYPES):
        return False, "File content type does not match JSON upload requirements."
    if extension in {".xml", ".xlml"} and content_type and content_type not in XML_UPLOAD_CONTENT_TYPES.union(TEXT_UPLOAD_CONTENT_TYPES):
        return False, "File content type does not match XML upload requirements."
    if extension == ".txt" and content_type and content_type not in TEXT_UPLOAD_CONTENT_TYPES.union(CSV_UPLOAD_CONTENT_TYPES):
        return False, "File content type does not match TXT upload requirements."
    if extension == ".parquet" and content_type and content_type not in PARQUET_UPLOAD_CONTENT_TYPES:
        return False, "File content type does not match Parquet upload requirements."

    file_head = uploaded_file.read(4096)
    uploaded_file.seek(0)

    if extension in {".csv", ".json", ".xml", ".xlml", ".txt", ".sql"}:
        if b"\x00" in file_head:
            return False, "Potentially unsafe text upload detected (binary payload)."
        try:
            head_text = file_head.decode("utf-8")
        except UnicodeDecodeError:
            try:
                head_text = file_head.decode("latin-1")
            except UnicodeDecodeError:
                return False, "Text file encoding is not supported."

        suspicious_tokens = (
            "<script",
            "javascript:",
            "<?php",
            "<iframe",
            "powershell",
            "cmd.exe",
        )
        lowered = head_text.lower()
        if any(token in lowered for token in suspicious_tokens):
            return False, "Potentially malicious content detected in uploaded text file."

        if extension == ".json" and not lowered.lstrip().startswith(('{', '[')):
            return False, "Invalid JSON structure detected."

        if extension in {".xml", ".xlml"} and not lowered.lstrip().startswith('<'):
            return False, "Invalid XML structure detected."

    if extension == ".xlsx" and not file_head.startswith(b"PK"):
        return False, "Invalid XLSX archive signature."
    if extension == ".parquet" and not file_head.startswith(b"PAR1"):
        return False, "Invalid Parquet file signature."

    return True, None


def _apply_analysis_limits(df, context):
    notices = []
    max_rows = settings.MAX_ANALYSIS_ROWS
    max_columns = settings.MAX_ANALYSIS_COLUMNS

    if df.shape[1] > max_columns:
        df = df.iloc[:, :max_columns].copy()
        notices.append(f"Limited analysis to first {max_columns} columns for performance.")

    if df.shape[0] > max_rows:
        df = df.head(max_rows).copy()
        notices.append(f"Limited analysis to first {max_rows} rows for performance.")

    if notices:
        prior_info = context.get("info")
        context["info"] = " ".join([prior_info] + notices) if prior_info else " ".join(notices)

    return df


def _build_stakeholder_brief_text(context):
    analyst_brief = context.get('analyst_brief') or {}
    recommendations = analyst_brief.get('recommendations', [])
    signals = analyst_brief.get('quality_signals', [])
    alerts = context.get('anomaly_alerts', [])
    suggestions = context.get('chart_suggestions', [])

    dataset_label = context.get('uploaded_file_name') or context.get('selected_dataset') or 'dataset'
    generated_at = timezone.now().strftime('%Y-%m-%d %H:%M UTC')

    lines = [
        "Stakeholder Brief - DataViz Pro",
        f"Generated: {generated_at}",
        f"Dataset: {dataset_label}",
        "",
        "Executive Auto-Insights",
        "-----------------------",
    ]

    if signals:
        lines.append("Data Quality Signals:")
        for signal in signals:
            level = str(signal.get('level', 'info')).upper()
            lines.append(f"- [{level}] {signal.get('title', '')}: {signal.get('detail', '')}")
    else:
        lines.append("Data Quality Signals: No notable issues detected.")

    lines.append("")
    lines.append("Automatic Anomaly Alerts:")
    if alerts:
        for item in alerts:
            lines.append(
                f"- {item.get('date')} | {item.get('metric')} {item.get('direction')} | value={item.get('value')} | score={item.get('score')}"
            )
    else:
        lines.append("- No major anomalies detected for the selected metric/date combination.")

    lines.append("")
    lines.append("Recommended Chart Types:")
    for suggestion in suggestions:
        lines.append(f"- {suggestion.get('plot_type')}: {suggestion.get('reason')}")

    lines.append("")
    lines.append("Recommended Actions:")
    if recommendations:
        for action in recommendations:
            lines.append(f"- {action}")
    else:
        lines.append("- Continue with dashboard monitoring and periodic data-quality checks.")

    return "\n".join(lines)


def _pdf_escape_text(value):
    return value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _build_stakeholder_brief_pdf(brief_text):
    raw_lines = []
    for line in str(brief_text).splitlines():
        wrapped = textwrap.wrap(line, width=96) or ['']
        raw_lines.extend(wrapped)

    if not raw_lines:
        raw_lines = ['Stakeholder Brief']

    lines_per_page = 48
    pages = [raw_lines[i:i + lines_per_page] for i in range(0, len(raw_lines), lines_per_page)]

    object_count = 3 + (2 * len(pages))
    content_ids = []
    page_ids = []

    next_id = 4
    for _ in pages:
        page_ids.append(next_id)
        content_ids.append(next_id + 1)
        next_id += 2

    objects = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids_ref = ' '.join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids_ref}] >>".encode('ascii')
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for idx, page_lines in enumerate(pages):
        page_id = page_ids[idx]
        content_id = content_ids[idx]

        commands = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
        for line in page_lines:
            commands.append(f"({_pdf_escape_text(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream_data = ('\n'.join(commands) + '\n').encode('latin-1', errors='replace')

        objects[content_id] = b"<< /Length " + str(len(stream_data)).encode('ascii') + b" >>\nstream\n" + stream_data + b"endstream"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode('ascii')

    buffer = bytearray()
    buffer.extend(b"%PDF-1.4\n")
    offsets = [0] * (object_count + 1)

    for object_id in range(1, object_count + 1):
        offsets[object_id] = len(buffer)
        buffer.extend(f"{object_id} 0 obj\n".encode('ascii'))
        buffer.extend(objects[object_id])
        buffer.extend(b"\nendobj\n")

    xref_start = len(buffer)
    buffer.extend(f"xref\n0 {object_count + 1}\n".encode('ascii'))
    buffer.extend(b"0000000000 65535 f \n")
    for object_id in range(1, object_count + 1):
        buffer.extend(f"{offsets[object_id]:010d} 00000 n \n".encode('ascii'))

    buffer.extend(
        (
            f"trailer\n<< /Size {object_count + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode('ascii')
    )

    return bytes(buffer)


def health_check(request):
    started = time.monotonic()
    db_ok = True
    db_error = None

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "timestamp": timezone.now().isoformat(),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    if db_error:
        payload["database_error"] = db_error

    return JsonResponse(payload, status=200 if db_ok else 503)

# -----------------------------
# Core Pages
# -----------------------------

def home(request):
    context = {
        'dataset_options': data_processor.DATASET_OPTIONS,
        'selected_dataset': request.session.get('selected_dataset'),
        'uploaded_file_name': request.session.get('uploaded_file_name'),
    }
    return render(request, 'dataviz/home.html', context)


def newsletter_subscribe(request):
    fallback_url = reverse("dataviz:home")
    redirect_target = request.POST.get("next") or request.META.get("HTTP_REFERER") or fallback_url

    if not url_has_allowed_host_and_scheme(
        url=redirect_target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_target = fallback_url

    if request.method != "POST":
        return redirect(redirect_target)

    form = NewsletterSubscriptionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid email address.")
        return redirect(redirect_target)

    normalized_email = form.cleaned_data["email"].strip().lower()
    subscriber, created = NewsletterSubscriber.objects.get_or_create(
        email=normalized_email,
        defaults={"is_active": True},
    )

    if created:
        messages.success(request, "You are subscribed. You will receive updates for new blogs and datasets.")
    elif not subscriber.is_active:
        subscriber.is_active = True
        subscriber.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Your newsletter subscription has been reactivated.")
    else:
        messages.info(request, "This email is already subscribed.")

    return redirect(redirect_target)

def datasets(request):
    can_manage_datasets = request.user.is_authenticated and request.user.is_staff

    def get_post_login_download_dataset():
        if not request.user.is_authenticated:
            return None

        requested_id = (request.GET.get("download") or "").strip()
        if not requested_id.isdigit():
            return None

        return StoredDataset.objects.filter(pk=int(requested_id), is_active=True).first()

    store_sort_map = {
        'relevance': ('-relevance_score', '-created_at'),
        'newest': ('-created_at',),
        'oldest': ('created_at',),
        'title_asc': ('title',),
        'title_desc': ('-title',),
        'downloads_desc': ('-download_count', '-created_at'),
        'downloads_asc': ('download_count', '-created_at'),
    }
    store_sort_options = [
        ('relevance', 'Best match'),
        ('newest', 'Newest first'),
        ('oldest', 'Oldest first'),
        ('title_asc', 'Title A-Z'),
        ('title_desc', 'Title Z-A'),
        ('downloads_desc', 'Most downloads'),
        ('downloads_asc', 'Least downloads'),
    ]
    store_file_type_options = [('all', 'All types')]
    for extension in settings.ALLOWED_UPLOAD_EXTENSIONS:
        clean_ext = extension.lstrip('.').lower()
        store_file_type_options.append((clean_ext, clean_ext.upper()))

    tag_options = [('all', 'All tags')]
    available_tags = DatasetTag.objects.filter(datasets__is_active=True).distinct().order_by('name')
    tag_options.extend((tag.slug, tag.name) for tag in available_tags)

    def build_store_listing_context():
        search_query = (request.GET.get('q') or '').strip()
        requested_sort = (request.GET.get('sort') or '').strip().lower()
        selected_sort = requested_sort or ('relevance' if search_query else 'newest')
        selected_file_type = (request.GET.get('file_type') or 'all').strip().lower()
        selected_owner = (request.GET.get('owner') or 'all').strip().lower()
        selected_tag = (request.GET.get('tag') or 'all').strip().lower()

        if selected_sort not in store_sort_map:
            selected_sort = 'relevance' if search_query else 'newest'

        if not search_query and selected_sort == 'relevance':
            selected_sort = 'newest'

        valid_file_types = {option[0] for option in store_file_type_options}
        if selected_file_type not in valid_file_types:
            selected_file_type = 'all'

        valid_tags = {option[0] for option in tag_options}
        if selected_tag not in valid_tags:
            selected_tag = 'all'

        if selected_owner not in {'all', 'mine'}:
            selected_owner = 'all'

        queryset = StoredDataset.objects.filter(is_active=True).select_related('uploaded_by').prefetch_related('tags')

        if search_query:
            queryset = queryset.annotate(
                relevance_score=(
                    Case(
                        When(title__iexact=search_query, then=Value(250)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                    + Case(
                        When(title__istartswith=search_query, then=Value(150)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                    + Case(
                        When(title__icontains=search_query, then=Value(100)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                    + Case(
                        When(description__icontains=search_query, then=Value(60)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                    + Case(
                        When(original_filename__icontains=search_query, then=Value(70)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                    + Case(
                        When(uploaded_by__username__icontains=search_query, then=Value(40)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                    + Case(
                        When(tags__name__icontains=search_query, then=Value(80)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                )
            ).filter(
                Q(title__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(original_filename__icontains=search_query)
                | Q(uploaded_by__username__icontains=search_query)
                | Q(tags__name__icontains=search_query)
            )
        else:
            queryset = queryset.annotate(relevance_score=Value(0, output_field=IntegerField()))

        if selected_file_type != 'all':
            queryset = queryset.filter(
                Q(original_filename__iendswith=f'.{selected_file_type}')
                | Q(dataset_file__iendswith=f'.{selected_file_type}')
            )

        if selected_tag != 'all':
            queryset = queryset.filter(tags__slug=selected_tag)

        if selected_owner == 'mine':
            if request.user.is_authenticated:
                queryset = queryset.filter(uploaded_by=request.user)
            else:
                selected_owner = 'all'

        queryset = queryset.distinct()
        queryset = queryset.order_by(*store_sort_map[selected_sort])

        paginator = Paginator(queryset, 8)
        page_obj = paginator.get_page(request.GET.get('page'))

        query_params = request.GET.copy()
        query_params.pop('page', None)

        return {
            'store_datasets': page_obj.object_list,
            'store_page_obj': page_obj,
            'store_total_count': paginator.count,
            'store_q': search_query,
            'store_sort': selected_sort,
            'store_file_type': selected_file_type,
            'store_owner': selected_owner,
            'store_tag': selected_tag,
            'store_sort_options': store_sort_options,
            'store_file_type_options': store_file_type_options,
            'store_tag_options': tag_options,
            'store_query_string': query_params.urlencode(),
            'store_has_filters': (
                bool(search_query)
                or selected_file_type != 'all'
                or selected_owner != 'all'
                or selected_tag != 'all'
            ),
        }

    context = {
        'uploaded_file_name': request.session.get('uploaded_file_name'),
        'uploaded_file_description': request.session.get('uploaded_file_description', ''),
        'max_upload_size_mb': settings.MAX_UPLOAD_SIZE_MB,
        'can_manage_datasets': can_manage_datasets,
        'post_login_download_dataset': get_post_login_download_dataset(),
        'store_title': '',
        'store_description': '',
        'store_tags': '',
        **build_store_listing_context(),
    }

    if request.method == 'POST':
        if request.POST.get('store_dataset_submit') == '1':
            context['store_title'] = (request.POST.get('store_title') or '').strip()
            context['store_description'] = (request.POST.get('store_description') or '').strip()
            context['store_tags'] = (request.POST.get('store_tags') or '').strip()
            if len(context['store_description']) > 2000:
                context['store_description'] = context['store_description'][:2000]

            store_file = request.FILES.get('store_file_upload')
            if not can_manage_datasets:
                context['store_error'] = "You do not have permission to publish datasets to the shared store."
            elif not context['store_title']:
                context['store_error'] = "Please provide a dataset title."
            elif not context['store_description']:
                context['store_error'] = "Please provide a dataset explanation before uploading."
            elif not store_file:
                context['store_error'] = "Please choose a file for the dataset store upload."
            else:
                is_valid_upload, upload_error = _validate_uploaded_file(store_file)
                if not is_valid_upload:
                    logger.warning(
                        "Rejected dataset store upload",
                        extra={
                            "uploaded_filename": store_file.name,
                            "content_type": store_file.content_type,
                            "upload_size": store_file.size,
                            "uploaded_by": request.user.username,
                        },
                    )
                    context['store_error'] = upload_error
                else:
                    dataset_instance = StoredDataset.objects.create(
                        title=context['store_title'],
                        description=context['store_description'],
                        dataset_file=store_file,
                        original_filename=store_file.name,
                        uploaded_by=request.user,
                    )

                    parsed_tag_names = _parse_dataset_tags(context['store_tags'])
                    if parsed_tag_names:
                        tag_objects = []
                        for tag_name in parsed_tag_names:
                            tag_instance = DatasetTag.objects.filter(name__iexact=tag_name).first()
                            if tag_instance is None:
                                tag_instance = DatasetTag.objects.create(name=tag_name)
                            tag_objects.append(tag_instance)
                        dataset_instance.tags.set(tag_objects)

                    context['store_success'] = "Dataset added to store successfully."
                    context['store_title'] = ''
                    context['store_description'] = ''
                    context['store_tags'] = ''

        else:
            if not can_manage_datasets:
                context['error'] = "You do not have permission to upload datasets from this page."
                context.update(build_store_listing_context())
                return render(request, "dataviz/datasets.html", context)

            uploaded_file = request.FILES.get('file_upload')
            dataset_explanation = (request.POST.get('dataset_explanation') or '').strip()
            if len(dataset_explanation) > 1200:
                dataset_explanation = dataset_explanation[:1200]

            request.session['uploaded_file_description'] = dataset_explanation
            context['uploaded_file_description'] = dataset_explanation

            if not uploaded_file:
                context['error'] = "Please choose a dataset file before uploading."
                return render(request, "dataviz/datasets.html", context)

            is_valid_upload, upload_error = _validate_uploaded_file(uploaded_file)
            if not is_valid_upload:
                logger.warning(
                    "Rejected upload on datasets page",
                    extra={
                        "uploaded_filename": uploaded_file.name,
                        "content_type": uploaded_file.content_type,
                        "upload_size": uploaded_file.size,
                    },
                )
                context['error'] = upload_error
                return render(request, "dataviz/datasets.html", context)

            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)
            uploaded_file_path = os.path.join(settings.MEDIA_ROOT, filename)

            request.session['uploaded_file_path'] = uploaded_file_path
            request.session['uploaded_file_name'] = uploaded_file.name
            request.session['selected_dataset'] = None

            context['uploaded_file_name'] = uploaded_file.name
            context['success'] = "Dataset uploaded successfully. You can now continue to analysis."

        context.update(build_store_listing_context())
        context['post_login_download_dataset'] = get_post_login_download_dataset()

    return render(request, "dataviz/datasets.html", context)


@login_required
def dataset_store_download(request, dataset_id):
    dataset = get_object_or_404(StoredDataset, pk=dataset_id, is_active=True)
    if not dataset.dataset_file:
        raise Http404("Dataset file is not available.")

    StoredDataset.objects.filter(pk=dataset.pk).update(download_count=F('download_count') + 1)

    try:
        file_handle = dataset.dataset_file.open('rb')
    except FileNotFoundError as exc:
        raise Http404("Dataset file was not found on server.") from exc

    return FileResponse(file_handle, as_attachment=True, filename=dataset.download_name)

def features(request):
    return render(request, "dataviz/features.html")

def online_data_visualization(request):
    return render(request, "dataviz/online_data_visualization.html")

def python_data_visualization(request):
    return render(request, "dataviz/python_data_visualization.html")

def data_visualization_dashboard(request):
    return render(request, "dataviz/data_visualization_dashboard.html")

def about(request):
    return render(request, 'dataviz/about.html')

# -----------------------------
# Tools Pages
# -----------------------------

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
    return render(request, "dataviz/python_visualization_examples.html")

# -----------------------------
# Use Case Pages
# -----------------------------

def student_performance_data(request):
    return render(request, "dataviz/student_performance_data.html")

def global_sales_2024(request):
    return render(request, "dataviz/global_sales_2024.html")

def visualize_sales_data(request):
    return render(request, "dataviz/use_cases/visualize_sales_data.html")

def visualize_financial_data(request):
    return render(request, "dataviz/use_cases/visualize_financial_data.html")

def visualize_healthcare_data(request):
    return render(request, "dataviz/use_cases/visualize_healthcare_data.html")

def compare_tableau(request):
    return render(request, "dataviz/use_cases/compare_tableau.html")

def compare_powerbi(request):
    return render(request, "dataviz/use_cases/compare_powerbi.html")

def dataviz_vs_excel(request):
    return render(request, "dataviz/use_cases/dataviz_vs_excel.html")

def dataviz_vs_google_sheets(request):
    return render(request, "dataviz/use_cases/dataviz_vs_google_sheets.html")

def dataviz_vs_plotly(request):
    return render(request, "dataviz/use_cases/dataviz_vs_plotly.html")

# -----------------------------
# Blog Pages
# -----------------------------

def blog_index(request):
    posts = Blog.objects.all().order_by('-created_at')
    return render(request, "dataviz/blog/index.html", {"posts": posts})

def blog_dynamic(request, slug):
    post = get_object_or_404(Blog, slug=slug)
    related_posts = Blog.objects.exclude(pk=post.pk).order_by('-created_at')[:3]
    return render(
        request,
        "dataviz/blog/dynamic_post.html",
        {
            "post": post,
            "related_posts": related_posts,
        },
    )

# -----------------------------
# Data Utilities
# -----------------------------

def get_dataframe(request):
    uploaded_file_path = request.session.get('uploaded_file_path')
    if uploaded_file_path and os.path.exists(uploaded_file_path):
        df, error = data_processor.load_dataset(file_path=uploaded_file_path)
        return df, error
    sample_name = request.session.get('selected_dataset', 'iris')
    return data_processor.load_dataset(sample_name=sample_name)

# -----------------------------
# Analysis View
# -----------------------------

def data_analysis(request):
    plot_types_2d = ["Line", "Bar", "Scatter", "Histogram", "KDE"]
    plot_types_3d = ["3D Scatter", "3D Surface"]
    plot_types_geo = ["Geo Scatter", "Geo Density", "Geo Choropleth"]
    chart_types = plot_types_2d + plot_types_3d + plot_types_geo

    plot_family_to_types = {
        '2d': plot_types_2d,
        '3d': plot_types_3d,
        'geo': plot_types_geo,
    }

    def _family_from_plot_type(plot_type_value):
        if plot_type_value in plot_types_3d:
            return '3d'
        if plot_type_value in plot_types_geo:
            return 'geo'
        return '2d'

    advanced_plot_types = {"3D Scatter", "3D Surface", "Geo Scatter", "Geo Density", "Geo Choropleth"}
    geo_scope_options = [
        "world",
        "usa",
        "europe",
        "asia",
        "africa",
        "north america",
        "south america",
    ]
    geo_map_style_options = [
        "open-street-map",
        "carto-positron",
        "carto-darkmatter",
        "stamen-terrain",
        "stamen-toner",
    ]
    geo_projection_options = [
        "natural earth",
        "equirectangular",
        "mercator",
        "orthographic",
        "robinson",
    ]
    geo_location_mode_options = [
        "country names",
        "ISO-3",
        "USA-states",
    ]
    geo_choropleth_color_scale_options = [
        "Blues",
        "Viridis",
        "YlOrRd",
        "Plasma",
    ]
    dashboard_presets = data_processor.get_dashboard_presets()
    preset_labels = {preset['value']: preset['label'] for preset in dashboard_presets}
    apply_dashboard_preset = False
    export_narrative_requested = False
    export_narrative_format = 'txt'
    apply_chart_suggestion = False
    stage_order_by_preset = _get_stage_order_map(request.session)
    initial_preset = request.session.get('dashboard_preset', 'retail_sales')
    initial_stage_order = stage_order_by_preset.get(
        initial_preset,
        request.session.get('dashboard_stage_order_input', ''),
    )

    context = {
        'dataset_options': data_processor.DATASET_OPTIONS,
        'selected_dataset': request.session.get('selected_dataset', 'iris'),
        'uploaded_file_name': request.session.get('uploaded_file_name'),
        'uploaded_file_description': request.session.get('uploaded_file_description', ''),
        'plot_family': '2d',
        'plot_type': 'Scatter',
        'plot_types_2d': plot_types_2d,
        'plot_types_3d': plot_types_3d,
        'plot_types_geo': plot_types_geo,
        'plot_type_2d': 'Scatter',
        'plot_type_3d': plot_types_3d[0],
        'plot_type_geo': plot_types_geo[0],
        'x_col': None,
        'y_col': None,
        'z_col': None,
        'size_col': None,
        'plot_color_col': None,
        'geo_lat_col': None,
        'geo_lon_col': None,
        'geo_location_col': None,
        'geo_year_col': None,
        'geo_scope': 'world',
        'geo_map_style': 'carto-positron',
        'geo_projection': 'natural earth',
        'geo_location_mode': 'country names',
        'geo_choropleth_color_scale': 'Blues',
        'hue_col': None,
        'chart_types': chart_types,
        'geo_scope_options': geo_scope_options,
        'geo_map_style_options': geo_map_style_options,
        'geo_projection_options': geo_projection_options,
        'geo_location_mode_options': geo_location_mode_options,
        'geo_choropleth_color_scale_options': geo_choropleth_color_scale_options,
        'geo_year_options': [],
        'dark_mode': request.session.get('dark_mode', False),
        'dashboard_metric': None,
        'dashboard_secondary_metric': None,
        'dashboard_category': None,
        'dashboard_date': None,
        'dashboard_stage_order_input': initial_stage_order,
        'dashboard_panel_count': 6,
        'dashboard_metric_options': [],
        'dashboard_category_options': [],
        'dashboard_date_options': [],
        'dashboard_panels': [],
        'dashboard_error': None,
        'dashboard_presets': dashboard_presets,
        'dashboard_preset': initial_preset,
        'dashboard_stage_candidates': [],
        'dashboard_stage_column': None,
        'dashboard_stage_order_list': [],
        'dashboard_command_center': None,
        'interactive_plot_html': None,
        'analyst_brief': None,
        'anomaly_alerts': [],
        'chart_suggestions': [],
        'suggestion_applied': False,
    }

    if request.method == 'POST':
        export_narrative_requested = request.POST.get('export_narrative') == '1'
        export_narrative_format = (request.POST.get('export_narrative_format') or 'txt').strip().lower()
        apply_chart_suggestion = request.POST.get('apply_chart_suggestion') == '1'

        if request.POST.get('toggle_dark'):
            request.session['dark_mode'] = not request.session.get('dark_mode', False)
            context['dark_mode'] = request.session['dark_mode']

        if 'dataset_select' in request.POST:
            selected_dataset = request.POST.get('dataset_select')
            request.session['selected_dataset'] = selected_dataset
            request.session['uploaded_file_path'] = None
            request.session['uploaded_file_name'] = None
            request.session['uploaded_file_description'] = ''
            context['selected_dataset'] = selected_dataset
            context['uploaded_file_description'] = ''

        elif 'file_upload' in request.FILES:
            uploaded_file = request.FILES['file_upload']

            is_valid_upload, upload_error = _validate_uploaded_file(uploaded_file)
            if not is_valid_upload:
                logger.warning(
                    "Rejected upload",
                    extra={
                        "uploaded_filename": uploaded_file.name,
                        "content_type": uploaded_file.content_type,
                        "upload_size": uploaded_file.size,
                    },
                )
                context['error'] = upload_error
                return render(request, 'dataviz/analysis.html', context)

            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)
            uploaded_file_path = os.path.join(settings.MEDIA_ROOT, filename)
            request.session['uploaded_file_path'] = uploaded_file_path
            request.session['uploaded_file_name'] = uploaded_file.name
            request.session['uploaded_file_description'] = ''
            request.session['selected_dataset'] = None
            context['selected_dataset'] = None
            context['uploaded_file_name'] = uploaded_file.name
            context['uploaded_file_description'] = ''

        context['x_col'] = request.POST.get('x_col_select')
        context['y_col'] = request.POST.get('y_col_select')
        context['z_col'] = request.POST.get('z_col_select')
        context['size_col'] = request.POST.get('size_col_select')
        context['plot_color_col'] = request.POST.get('plot_color_col_select')
        context['geo_lat_col'] = request.POST.get('geo_lat_col_select')
        context['geo_lon_col'] = request.POST.get('geo_lon_col_select')
        context['geo_location_col'] = request.POST.get('geo_location_col_select')
        context['geo_year_col'] = request.POST.get('geo_year_col_select')

        for key in ['x_col', 'y_col', 'z_col', 'size_col', 'plot_color_col', 'geo_lat_col', 'geo_lon_col', 'geo_location_col', 'geo_year_col']:
            if context.get(key) == 'None':
                context[key] = None

        posted_plot_family = request.POST.get('plot_family_select')
        if posted_plot_family in plot_family_to_types:
            context['plot_family'] = posted_plot_family

        posted_plot_type_direct = request.POST.get('plot_type_select')
        posted_plot_type_2d = request.POST.get('plot_type_2d_select')
        posted_plot_type_3d = request.POST.get('plot_type_3d_select')
        posted_plot_type_geo = request.POST.get('plot_type_geo_select')

        chosen_plot_type = None
        family_types = plot_family_to_types[context['plot_family']]

        family_specific_map = {
            '2d': posted_plot_type_2d,
            '3d': posted_plot_type_3d,
            'geo': posted_plot_type_geo,
        }
        if family_specific_map.get(context['plot_family']) in family_types:
            chosen_plot_type = family_specific_map[context['plot_family']]
        elif posted_plot_type_direct in family_types:
            chosen_plot_type = posted_plot_type_direct
        elif posted_plot_type_direct in chart_types:
            chosen_plot_type = posted_plot_type_direct

        if chosen_plot_type not in chart_types:
            chosen_plot_type = context['plot_type']

        if chosen_plot_type not in chart_types:
            chosen_plot_type = 'Scatter'

        context['plot_type'] = chosen_plot_type
        context['plot_family'] = _family_from_plot_type(context['plot_type'])

        posted_geo_scope = request.POST.get('geo_scope_select')
        if posted_geo_scope in geo_scope_options:
            context['geo_scope'] = posted_geo_scope

        posted_geo_style = request.POST.get('geo_map_style_select')
        if posted_geo_style in geo_map_style_options:
            context['geo_map_style'] = posted_geo_style

        posted_geo_projection = request.POST.get('geo_projection_select')
        if posted_geo_projection in geo_projection_options:
            context['geo_projection'] = posted_geo_projection

        posted_geo_location_mode = request.POST.get('geo_location_mode_select')
        if posted_geo_location_mode in geo_location_mode_options:
            context['geo_location_mode'] = posted_geo_location_mode

        posted_geo_choropleth_color_scale = request.POST.get('geo_choropleth_color_scale_select')
        if posted_geo_choropleth_color_scale in geo_choropleth_color_scale_options:
            context['geo_choropleth_color_scale'] = posted_geo_choropleth_color_scale

        context['hue_col'] = request.POST.get('hue_col_select')
        if context['hue_col'] == 'None':
            context['hue_col'] = None

        context['dashboard_metric'] = request.POST.get('dashboard_metric_select')
        context['dashboard_secondary_metric'] = request.POST.get('dashboard_secondary_metric_select')
        if context['dashboard_secondary_metric'] == 'None':
            context['dashboard_secondary_metric'] = None

        context['dashboard_category'] = request.POST.get('dashboard_category_select')
        if context['dashboard_category'] == 'None':
            context['dashboard_category'] = None

        context['dashboard_date'] = request.POST.get('dashboard_date_select')
        if context['dashboard_date'] == 'None':
            context['dashboard_date'] = None

        panel_count_raw = request.POST.get('dashboard_panel_count_select')
        if panel_count_raw in ['4', '6']:
            context['dashboard_panel_count'] = int(panel_count_raw)

        posted_preset = request.POST.get('dashboard_preset_select')
        if posted_preset in preset_labels:
            context['dashboard_preset'] = posted_preset
            request.session['dashboard_preset'] = posted_preset

        stage_order_input = request.POST.get('dashboard_stage_order_input')
        if stage_order_input is not None:
            context['dashboard_stage_order_input'] = stage_order_input.strip()
        else:
            context['dashboard_stage_order_input'] = stage_order_by_preset.get(context['dashboard_preset'], '')

        stage_order_by_preset[context['dashboard_preset']] = context['dashboard_stage_order_input']
        request.session['dashboard_stage_order_by_preset'] = stage_order_by_preset
        request.session['dashboard_stage_order_input'] = context['dashboard_stage_order_input']

        apply_dashboard_preset = request.POST.get('apply_dashboard_preset') == '1'

    df, error = get_dataframe(request)
    if error:
        context['error'] = error
        return render(request, 'dataviz/analysis.html', context)

    if df.empty:
        context['info'] = "Please select a dataset or upload a file to begin analysis."
        return render(request, 'dataviz/analysis.html', context)

    df = _apply_analysis_limits(df, context)

    context['overview'] = data_processor.get_data_overview(df)
    context['analyst_brief'] = data_processor.get_analyst_brief(df)
    numeric_cols = data_processor.get_numeric_columns(df)
    context['numeric_columns'] = numeric_cols
    context['all_columns'] = df.columns.tolist()

    dashboard_options = data_processor.get_dashboard_options(df)
    context['dashboard_metric_options'] = dashboard_options['numeric_columns']
    context['dashboard_category_options'] = dashboard_options['category_columns']
    context['dashboard_date_options'] = dashboard_options['date_columns']
    geo_year_options = list(dashboard_options['date_columns'])
    geo_year_options.extend(
        col for col in context['all_columns']
        if 'year' in str(col).lower() and col not in geo_year_options
    )
    context['geo_year_options'] = geo_year_options

    stage_candidates, stage_column = data_processor.get_funnel_stage_candidates(
        df,
        context['dashboard_category'],
    )
    context['dashboard_stage_candidates'] = stage_candidates
    context['dashboard_stage_column'] = stage_column

    manual_stage_order = _parse_stage_order_input(context['dashboard_stage_order_input'])
    if stage_candidates:
        existing = {value.lower() for value in manual_stage_order}
        combined = manual_stage_order + [value for value in stage_candidates if value.lower() not in existing]
    else:
        combined = manual_stage_order

    context['dashboard_stage_order_list'] = combined
    if not context['dashboard_stage_order_input'] and combined:
        context['dashboard_stage_order_input'] = ', '.join(combined)

    if apply_dashboard_preset:
        inferred = data_processor.infer_dashboard_preset_config(
            df,
            context['dashboard_preset'],
            dashboard_options,
        )
        context['dashboard_metric'] = inferred.get('metric')
        context['dashboard_secondary_metric'] = inferred.get('secondary_metric')
        context['dashboard_category'] = inferred.get('category')
        context['dashboard_date'] = inferred.get('date')
        if inferred.get('panel_count') in [4, 6]:
            context['dashboard_panel_count'] = inferred['panel_count']

        selected_label = preset_labels.get(context['dashboard_preset'], 'Dashboard')
        context['info'] = f"Applied preset: {selected_label}. You can still adjust selections manually."

    if context['dashboard_metric'] not in context['dashboard_metric_options']:
        context['dashboard_metric'] = dashboard_options['default_metric']

    if context['dashboard_secondary_metric'] not in context['dashboard_metric_options']:
        context['dashboard_secondary_metric'] = dashboard_options['default_secondary_metric']

    if context['dashboard_secondary_metric'] == context['dashboard_metric']:
        alternatives = [c for c in context['dashboard_metric_options'] if c != context['dashboard_metric']]
        context['dashboard_secondary_metric'] = alternatives[0] if alternatives else context['dashboard_secondary_metric']

    if context['dashboard_category'] not in context['dashboard_category_options']:
        context['dashboard_category'] = dashboard_options['default_category']

    if context['dashboard_date'] not in context['dashboard_date_options']:
        context['dashboard_date'] = dashboard_options['default_date']

    if context['dashboard_panel_count'] not in [4, 6]:
        context['dashboard_panel_count'] = 6

    context['dashboard_command_center'] = data_processor.get_dashboard_command_center(
        df,
        metric_col=context['dashboard_metric'],
        secondary_metric_col=context['dashboard_secondary_metric'],
        category_col=context['dashboard_category'],
        date_col=context['dashboard_date'],
    )

    if numeric_cols:
        context['x_col'] = context['x_col'] or numeric_cols[0]
        context['y_col'] = context['y_col'] or (numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0])
        context['z_col'] = context['z_col'] or (numeric_cols[2] if len(numeric_cols) > 2 else numeric_cols[-1])

        if context['size_col'] not in numeric_cols:
            context['size_col'] = next(
                (c for c in numeric_cols if c not in {context['x_col'], context['y_col'], context['z_col']}),
                None,
            )

    if context['x_col'] not in numeric_cols:
        context['x_col'] = numeric_cols[0] if numeric_cols else None
    if context['y_col'] not in numeric_cols:
        context['y_col'] = numeric_cols[1] if len(numeric_cols) > 1 else (numeric_cols[0] if numeric_cols else None)
    if context['z_col'] not in numeric_cols:
        context['z_col'] = numeric_cols[2] if len(numeric_cols) > 2 else (numeric_cols[-1] if numeric_cols else None)
    if context['size_col'] not in numeric_cols:
        context['size_col'] = None

    categorical_cols = data_processor.get_categorical_columns(df)
    if context['plot_color_col'] not in context['all_columns']:
        context['plot_color_col'] = categorical_cols[0] if categorical_cols else None

    if context['geo_lat_col'] not in numeric_cols:
        context['geo_lat_col'] = _pick_column_by_tokens(numeric_cols, ['lat', 'latitude'])
    if context['geo_lon_col'] not in numeric_cols:
        context['geo_lon_col'] = _pick_column_by_tokens(numeric_cols, ['lon', 'lng', 'longitude'])
    if context['geo_location_col'] not in context['all_columns']:
        context['geo_location_col'] = _pick_column_by_tokens(
            context['all_columns'],
            ['country', 'region', 'state', 'city', 'location'],
        )
    if context['geo_year_col'] not in context['geo_year_options']:
        context['geo_year_col'] = context['geo_year_options'][0] if context['geo_year_options'] else None

    if context['geo_scope'] not in geo_scope_options:
        context['geo_scope'] = 'world'
    if context['geo_map_style'] not in geo_map_style_options:
        context['geo_map_style'] = 'carto-positron'
    if context['geo_projection'] not in geo_projection_options:
        context['geo_projection'] = 'natural earth'
    if context['geo_location_mode'] not in geo_location_mode_options:
        context['geo_location_mode'] = 'country names'
    if context['geo_choropleth_color_scale'] not in geo_choropleth_color_scale_options:
        context['geo_choropleth_color_scale'] = 'Blues'

    context['plot_family'] = _family_from_plot_type(context['plot_type'])
    context['plot_type_2d'] = context['plot_type'] if context['plot_type'] in plot_types_2d else plot_types_2d[0]
    context['plot_type_3d'] = context['plot_type'] if context['plot_type'] in plot_types_3d else plot_types_3d[0]
    context['plot_type_geo'] = context['plot_type'] if context['plot_type'] in plot_types_geo else plot_types_geo[0]

    context['anomaly_alerts'] = data_processor.get_metric_anomaly_alerts(
        df,
        metric_col=context['dashboard_metric'] or context['y_col'],
        date_col=context['dashboard_date'],
    )
    context['chart_suggestions'] = data_processor.get_chart_suggestions(
        df,
        x_col=context['x_col'],
        y_col=context['y_col'],
    )

    if apply_chart_suggestion:
        suggestion_name = request.POST.get('suggestion_plot_type') or context['plot_type']
        context['info'] = f"Applied suggestion: {suggestion_name}. Review and adjust as needed."
        context['suggestion_applied'] = True

    if export_narrative_requested:
        brief_text = _build_stakeholder_brief_text(context)
        dataset_label = str(context.get('uploaded_file_name') or context.get('selected_dataset') or 'dataset').lower()
        safe_name = ''.join(ch if ch.isalnum() else '_' for ch in dataset_label).strip('_') or 'dataset'
        if export_narrative_format == 'pdf':
            pdf_bytes = _build_stakeholder_brief_pdf(brief_text)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="stakeholder_brief_{safe_name}.pdf"'
            return response

        response = HttpResponse(brief_text, content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="stakeholder_brief_{safe_name}.txt"'
        return response

    request_started = time.monotonic()

    dashboard_budget = _remaining_time_seconds(request_started)
    if dashboard_budget <= 0:
        context['dashboard_error'] = "Dashboard skipped due to analysis timeout budget."
    elif not context['dashboard_metric']:
        context['dashboard_error'] = "Dashboard requires at least one numeric metric column."
    else:
        context['dashboard_panels'] = data_processor.generate_dashboard_panels(
            df,
            metric_col=context['dashboard_metric'],
            secondary_metric_col=context['dashboard_secondary_metric'],
            category_col=context['dashboard_category'],
            date_col=context['dashboard_date'],
            panel_count=context['dashboard_panel_count'],
            preset_key=context['dashboard_preset'],
            stage_order=context['dashboard_stage_order_input'],
        )
        if not context['dashboard_panels']:
            context['dashboard_error'] = "Unable to build dashboard panels for the selected options."

    pairplot_budget = _remaining_time_seconds(request_started)
    if pairplot_budget <= 0:
        context['pairplot_img'], context['pairplot_error'] = None, "Pairplot skipped due to analysis timeout budget."
    elif df.shape[0] > 5000:
        context['pairplot_img'], context['pairplot_error'] = None, "Pairplot skipped for large dataset."
    else:
        context['pairplot_img'], context['pairplot_error'] = data_processor.generate_pairplot(df, context['hue_col'])

    heatmap_budget = _remaining_time_seconds(request_started)
    if heatmap_budget <= 0:
        context['heatmap_html'], context['heatmap_error'] = None, "Heatmap skipped due to analysis timeout budget."
    else:
        context['heatmap_html'], context['heatmap_error'] = data_processor.generate_correlation_heatmap(df)

    chart_budget = _remaining_time_seconds(request_started)
    if chart_budget <= 0:
        context['interactive_plot_img'], context['interactive_plot_html'], context['interactive_plot_error'] = (
            None,
            None,
            "Chart skipped due to analysis timeout budget.",
        )
    else:
        if context['plot_type'] in advanced_plot_types:
            context['interactive_plot_img'] = None
            context['interactive_plot_html'], context['interactive_plot_error'] = data_processor.generate_advanced_plotly_plot(
                df,
                plot_type=context['plot_type'],
                x_col=context['x_col'],
                y_col=context['y_col'],
                z_col=context['z_col'],
                color_col=context['plot_color_col'],
                size_col=context['size_col'],
                lat_col=context['geo_lat_col'],
                lon_col=context['geo_lon_col'],
                location_col=context['geo_location_col'],
                geo_scope=context['geo_scope'],
                geo_map_style=context['geo_map_style'],
                geo_projection=context['geo_projection'],
                geo_location_mode=context['geo_location_mode'],
                geo_choropleth_color_scale=context['geo_choropleth_color_scale'],
                animation_col=context['geo_year_col'],
            )
        else:
            context['interactive_plot_html'] = None
            context['interactive_plot_img'], context['interactive_plot_error'] = data_processor.generate_interactive_plot(
                df,
                context['x_col'],
                context['y_col'],
                context['plot_type'],
                hue=context['hue_col'],
            )

    total_analysis_time = time.monotonic() - request_started
    if total_analysis_time > settings.ANALYSIS_TIMEOUT_SECONDS:
        logger.warning(
            "Analysis exceeded timeout budget",
            extra={"elapsed_seconds": round(total_analysis_time, 2)},
        )
        context['info'] = (
            f"Analysis exceeded {settings.ANALYSIS_TIMEOUT_SECONDS}s budget. "
            "Result complexity was reduced for responsiveness."
        )

    return render(request, 'dataviz/analysis.html', context)
