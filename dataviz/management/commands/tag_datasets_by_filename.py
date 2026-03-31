from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from dataviz.models import DatasetTag, StoredDataset


DEFAULT_RULES = {
    "ai": [
        "ai",
        "model",
        "feature_importance",
        "cluster",
        "cv_results",
        "submission",
        "scenario",
    ],
    "sports": [
        "odi",
        "t20",
        "batting",
        "bowling",
        "match",
        "matches",
        "squad",
        "squads",
        "venue",
        "venues",
        "scorecard",
        "tournament",
        "points",
        "podium",
        "cricket",
    ],
    "finance": [
        "gdp",
        "inflation",
        "macro",
        "economic",
        "economy",
        "trade",
        "stock",
        "wealth",
        "millionaire",
        "migration",
        "honda",
        "toyota",
        "tm_",
        "hmc_",
    ],
}


class Command(BaseCommand):
    help = "Apply tags to datasets based on filename keyword groups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--set-owner",
            type=str,
            default="",
            help="Optional username/email to assign as uploaded_by for all touched datasets",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview updates without writing to database",
        )

    def handle(self, *args, **options):
        target_owner = None
        owner_query = (options.get("set_owner") or "").strip()
        if owner_query:
            UserModel = get_user_model()
            target_owner = UserModel.objects.filter(username__iexact=owner_query).first()
            if target_owner is None:
                target_owner = UserModel.objects.filter(email__iexact=owner_query).first()
            if target_owner is None:
                raise CommandError(f"Owner not found by username/email: {owner_query}")

        dry_run = bool(options.get("dry_run"))
        tag_objects = {}
        if not dry_run:
            tag_objects = {
                tag_name: DatasetTag.objects.get_or_create(name=tag_name)[0]
                for tag_name in DEFAULT_RULES
            }

        touched = 0
        owner_updates = 0
        unmatched = 0
        matched_counts = {tag_name: 0 for tag_name in DEFAULT_RULES}

        for dataset in StoredDataset.objects.all():
            filename = ((dataset.original_filename or dataset.download_name or dataset.title) or "").lower()
            matched_tags = []
            for tag_name, keywords in DEFAULT_RULES.items():
                if any(keyword in filename for keyword in keywords):
                    matched_tags.append(tag_name)

            if not matched_tags:
                unmatched += 1
                continue

            touched += 1
            for tag_name in matched_tags:
                matched_counts[tag_name] += 1

            if dry_run:
                continue

            dataset.tags.add(*[tag_objects[tag_name] for tag_name in matched_tags])
            if target_owner is not None and dataset.uploaded_by_id != target_owner.id:
                dataset.uploaded_by = target_owner
                dataset.save(update_fields=["uploaded_by", "updated_at"])
                owner_updates += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run complete. No changes were written."))

        self.stdout.write(
            "\nSummary:\n"
            f"  Datasets touched: {touched}\n"
            f"  Unmatched datasets: {unmatched}\n"
            f"  Owner updates: {owner_updates}\n"
            f"  Tag matches: {matched_counts}"
        )
