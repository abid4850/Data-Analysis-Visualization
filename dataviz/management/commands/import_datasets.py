from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from dataviz.models import DatasetTag, StoredDataset


def _parse_tags(raw_text, max_tags=12):
    if not raw_text:
        return []

    chunks = [chunk.strip() for chunk in str(raw_text).replace("\n", ",").split(",") if chunk.strip()]
    seen = set()
    tags = []
    for chunk in chunks:
        normalized = " ".join(chunk.split())[:60]
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(normalized)
        if len(tags) >= max_tags:
            break
    return tags


def _title_from_filename(filename):
    base = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    if not base:
        base = "Dataset"
    return " ".join(base.split()).title()[:180]


class Command(BaseCommand):
    help = "Import dataset files from a local folder into the shared dataset store."

    def add_arguments(self, parser):
        parser.add_argument("directory", type=str, help="Absolute or relative folder path containing dataset files")
        parser.add_argument(
            "--recursive",
            action="store_true",
            help="Recursively scan subfolders for dataset files",
        )
        parser.add_argument(
            "--description",
            type=str,
            default="Imported from local dataset folder",
            help="Description applied to imported datasets",
        )
        parser.add_argument(
            "--tags",
            type=str,
            default="",
            help="Comma-separated tags to apply to each imported dataset",
        )
        parser.add_argument(
            "--owner",
            type=str,
            default="",
            help="Username or email for uploaded_by",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace existing records that have the same original filename",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview actions without writing to the database or storage",
        )

    def handle(self, *args, **options):
        target_dir = Path(options["directory"]).expanduser()
        if not target_dir.is_absolute():
            target_dir = Path.cwd() / target_dir
        target_dir = target_dir.resolve()

        if not target_dir.exists() or not target_dir.is_dir():
            raise CommandError(f"Directory does not exist: {target_dir}")

        allowed_extensions = {ext.lower() for ext in getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", set())}
        if not allowed_extensions:
            raise CommandError("ALLOWED_UPLOAD_EXTENSIONS is empty or not configured.")

        owner = None
        owner_query = (options.get("owner") or "").strip()
        if owner_query:
            UserModel = get_user_model()
            owner = UserModel.objects.filter(username__iexact=owner_query).first()
            if owner is None:
                owner = UserModel.objects.filter(email__iexact=owner_query).first()
            if owner is None:
                raise CommandError(f"Owner not found by username/email: {owner_query}")

        raw_tag_names = _parse_tags(options.get("tags", ""))
        tag_objects = []
        if raw_tag_names and not options["dry_run"]:
            for tag_name in raw_tag_names:
                tag_obj, _ = DatasetTag.objects.get_or_create(name=tag_name)
                tag_objects.append(tag_obj)

        file_iter = target_dir.rglob("*") if options["recursive"] else target_dir.glob("*")
        candidate_files = sorted(path for path in file_iter if path.is_file())

        imported_count = 0
        replaced_count = 0
        skipped_duplicates = 0
        skipped_unsupported = 0
        failed_count = 0

        for file_path in candidate_files:
            extension = file_path.suffix.lower()
            if extension not in allowed_extensions:
                skipped_unsupported += 1
                continue

            filename = file_path.name
            dataset_title = _title_from_filename(filename)
            existing = StoredDataset.objects.filter(original_filename=filename).order_by("-created_at").first()

            if existing and not options["replace"]:
                skipped_duplicates += 1
                continue

            action = "REPLACE" if existing else "IMPORT"
            if options["dry_run"]:
                self.stdout.write(f"[DRY-RUN] {action}: {filename}")
                continue

            try:
                with file_path.open("rb") as stream:
                    django_file = File(stream, name=filename)

                    if existing:
                        existing.title = dataset_title
                        existing.description = options["description"]
                        existing.original_filename = filename
                        existing.is_active = True
                        if owner is not None:
                            existing.uploaded_by = owner
                        existing.dataset_file.save(filename, django_file, save=False)
                        existing.save()
                        if tag_objects:
                            existing.tags.set(tag_objects)
                        replaced_count += 1
                    else:
                        new_dataset = StoredDataset(
                            title=dataset_title,
                            description=options["description"],
                            original_filename=filename,
                            uploaded_by=owner,
                            is_active=True,
                        )
                        new_dataset.dataset_file.save(filename, django_file, save=False)
                        new_dataset.save()
                        if tag_objects:
                            new_dataset.tags.set(tag_objects)
                        imported_count += 1

                self.stdout.write(self.style.SUCCESS(f"{action}: {filename}"))
            except Exception as exc:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f"FAILED: {filename} ({exc})"))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run complete. No files were imported."))

        self.stdout.write(
            "\nSummary:\n"
            f"  Imported: {imported_count}\n"
            f"  Replaced: {replaced_count}\n"
            f"  Skipped duplicates: {skipped_duplicates}\n"
            f"  Skipped unsupported: {skipped_unsupported}\n"
            f"  Failed: {failed_count}"
        )
