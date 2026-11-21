"""
python manage.py seed_files [--count N] [--reset]

Creates realistic demo files (50 PDFs + 50 images by default), encrypted and
stored exactly like real uploads, owned by the first superuser.

- Idempotent: each seeded file has a seed_key; files that already exist are
  skipped, even if they were renamed. Running it twice creates nothing new.
- --reset deletes all seeded files (records + .enc) first. Real uploads are
  never touched.
- Every generated file goes through files.validation.validate_file, the same
  rules as an HTTP upload.
"""

import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError

from files.models import FileRecord
from files.seed_content import all_specs
from files.validation import validate_file


class Command(BaseCommand):
    help = "Create encrypted demo PDFs and images (idempotent)."

    def add_arguments(self, parser):
        total = len(all_specs())
        parser.add_argument(
            "--count", type=int, default=total,
            help=f"How many files to seed, 1-{total} (alternating PDF/image). Default: {total}.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete all previously seeded files (records and .enc) before seeding.",
        )

    def handle(self, *args, count, reset, **options):
        specs = all_specs()
        if not 1 <= count <= len(specs):
            raise CommandError(f"--count must be between 1 and {len(specs)}.")

        owner = get_user_model().objects.filter(is_superuser=True).order_by("id").first()
        if owner is None:
            raise CommandError(
                "No superuser found. Seeded files are owned by the admin, so run "
                "'python manage.py createsuperuser' first."
            )

        if reset:
            seeded = FileRecord.objects.filter(seed_key__isnull=False)
            # Deleting records fires the post_delete signal, which removes each .enc.
            deleted, _ = seeded.delete()
            self.stdout.write(f"Reset: deleted {deleted} seeded file(s).")

        existing = set(FileRecord.objects.filter(seed_key__isnull=False).values_list("seed_key", flat=True))
        created = skipped = total_bytes = 0

        for spec in specs[:count]:
            if spec.name in existing:
                skipped += 1
                continue

            data = spec.build(random.Random(spec.name))  # same name -> same content
            try:
                upload = validate_file(spec.name, data)  # same rules as an HTTP upload
            except ValidationError as error:
                raise CommandError(f"Generated file {spec.name} failed validation: {error.detail}")

            FileRecord.create_from_upload(upload, owner=owner, seed_key=spec.name)
            created += 1
            total_bytes += len(data)

        self.stdout.write(self.style.SUCCESS(
            f"Created {created} file(s), skipped {skipped} already seeded, "
            f"{total_bytes / (1024 * 1024):.1f} MB of plaintext encrypted. Owner: {owner.username}."
        ))
