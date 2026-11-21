"""Tests for `manage.py seed_files` (Phase 6). Uses --count 4 to stay fast."""

import hashlib
import io
import re
from collections import Counter
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from PIL import Image

from .crypto import decrypt_bytes
from .models import FileRecord
from .seed_content import all_specs
from .storage import read_decrypted
from .test_api import make_jpg_bytes
from .tests import TempStorageMixin
from .validation import SIGNATURES, validate_file

User = get_user_model()


class SeedTestCase(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("boss", "boss@example.com")

    def seed(self, *args):
        out = io.StringIO()
        call_command("seed_files", *args, stdout=out)
        return out.getvalue()

    def seeded(self):
        return FileRecord.objects.filter(seed_key__isnull=False)


class SeedBasicsTests(SeedTestCase):
    def test_creates_count_files_alternating_pdf_and_image(self):
        output = self.seed("--count", "4")

        self.assertIn("Created 4 file(s), skipped 0", output)
        self.assertEqual(self.seeded().count(), 4)
        self.assertEqual(Counter(self.seeded().values_list("file_type", flat=True)),
                         {"pdf": 2, "image": 2})
        self.assertEqual(len(self.stored_files()), 4)

    def test_files_are_owned_by_the_superuser(self):
        User.objects.create_user("normal")  # not a superuser; must not become owner
        self.seed("--count", "4")

        self.assertEqual(set(self.seeded().values_list("uploaded_by__username", flat=True)), {"boss"})

    def test_no_superuser_gives_clear_error(self):
        self.admin.delete()

        with self.assertRaisesMessage(CommandError, "createsuperuser"):
            self.seed("--count", "4")
        self.assertFalse(FileRecord.objects.exists())

    def test_invalid_count_rejected(self):
        for bad in ("0", "101", "-3"):
            with self.subTest(count=bad):
                with self.assertRaises(CommandError):
                    self.seed("--count", bad)


class SeedContentTests(SeedTestCase):
    def setUp(self):
        super().setUp()
        self.seed("--count", "4")

    def test_stored_files_are_encrypted_and_match_sha256_and_size(self):
        for record in self.seeded():
            with self.subTest(file=record.original_name):
                on_disk = (self.storage_dir / record.stored_name).read_bytes()
                plaintext = decrypt_bytes(on_disk)
                self.assertNotEqual(on_disk, plaintext)
                self.assertEqual(hashlib.sha256(plaintext).hexdigest(), record.sha256)
                self.assertEqual(len(plaintext), record.size)

    def test_pdfs_are_real_multipage_pdfs(self):
        for record in self.seeded().filter(file_type="pdf"):
            with self.subTest(file=record.original_name):
                data = read_decrypted(record.stored_name)
                self.assertTrue(data.startswith(b"%PDF-"))
                pages = len(re.findall(rb"/Type /Page\b(?!s)", data))
                self.assertGreaterEqual(pages, 2)
                self.assertEqual(record.mime_type, "application/pdf")

    def test_images_open_with_pillow_and_match_mime(self):
        formats = {"image/png": "PNG", "image/jpeg": "JPEG"}
        for record in self.seeded().filter(file_type="image"):
            with self.subTest(file=record.original_name):
                image = Image.open(io.BytesIO(read_decrypted(record.stored_name)))
                self.assertEqual(image.format, formats[record.mime_type])
                self.assertGreater(image.width * image.height, 0)

    def test_seed_key_is_the_generated_name(self):
        for record in self.seeded():
            self.assertEqual(record.seed_key, record.original_name)


class SeedIdempotencyTests(SeedTestCase):
    def test_running_twice_creates_no_duplicates(self):
        self.seed("--count", "4")
        first_files = self.stored_files()

        output = self.seed("--count", "4")

        self.assertIn("Created 0 file(s), skipped 4", output)
        self.assertEqual(self.seeded().count(), 4)
        self.assertEqual(self.stored_files(), first_files)

    def test_higher_count_adds_only_the_missing_files(self):
        self.seed("--count", "4")

        output = self.seed("--count", "6")

        self.assertIn("Created 2 file(s), skipped 4", output)
        self.assertEqual(self.seeded().count(), 6)

    def test_renamed_seeded_file_is_not_recreated(self):
        self.seed("--count", "4")
        record = self.seeded().first()
        record.original_name = "renamed by a user.pdf"
        record.save()

        self.seed("--count", "4")

        self.assertEqual(self.seeded().count(), 4)


class SeedResetTests(SeedTestCase):
    def test_reset_replaces_seeded_files_and_their_enc(self):
        self.seed("--count", "4")
        old_enc = set(self.stored_files())

        with self.captureOnCommitCallbacks(execute=True):  # .enc deletion runs on commit
            output = self.seed("--count", "4", "--reset")

        self.assertIn("Reset: deleted 4 seeded file(s).", output)
        self.assertIn("Created 4 file(s)", output)
        self.assertEqual(self.seeded().count(), 4)
        new_enc = set(self.stored_files())
        self.assertEqual(len(new_enc), 4)
        self.assertFalse(old_enc & new_enc)  # every old .enc is gone

    def test_reset_never_touches_real_uploads(self):
        user = User.objects.create_user("alice")
        real = FileRecord.create_from_upload(validate_file("holiday.jpg", make_jpg_bytes()), owner=user)
        self.seed("--count", "4")

        with self.captureOnCommitCallbacks(execute=True):
            self.seed("--count", "4", "--reset")

        self.assertTrue(FileRecord.objects.filter(id=real.id).exists())
        self.assertTrue((self.storage_dir / real.stored_name).exists())


class SeedValidationTests(SeedTestCase):
    def test_generated_file_failing_validation_aborts_with_clear_error(self):
        # Make the first spec produce bytes that aren't a real PDF.
        broken = [all_specs()[0]._replace(build=lambda rng: b"not really a pdf")]
        with mock.patch("files.management.commands.seed_files.all_specs", return_value=broken):
            with self.assertRaisesMessage(CommandError, "failed validation"):
                self.seed("--count", "1")

        self.assertFalse(FileRecord.objects.exists())
        self.assertEqual(self.stored_files(), [])

    def test_seed_uses_the_shared_validate_file(self):
        with mock.patch(
            "files.management.commands.seed_files.validate_file", wraps=validate_file
        ) as spy:
            self.seed("--count", "4")

        self.assertEqual(spy.call_count, 4)


class CatalogueTests(TestCase):
    """Checks the full 100-file list without generating any content (fast)."""

    def test_catalogue_is_50_pdfs_and_50_images_with_unique_names(self):
        names = [spec.name for spec in all_specs()]

        self.assertEqual(len(names), 100)
        self.assertEqual(len(set(names)), 100)
        extensions = Counter(name.rsplit(".", 1)[1] for name in names)
        self.assertEqual(extensions["pdf"], 50)
        self.assertEqual(extensions["png"] + extensions["jpg"], 50)
        self.assertGreater(extensions["png"], 0)
        self.assertGreater(extensions["jpg"], 0)

    def test_every_extension_is_allowed_by_validation(self):
        allowed = set().union(*(exts for *_, exts in SIGNATURES))
        for spec in all_specs():
            self.assertIn("." + spec.name.rsplit(".", 1)[1], allowed)

    def test_catalogue_covers_the_demo_categories(self):
        names = " ".join(spec.name for spec in all_specs())
        for prefix in ["invoice_", "report_", "certificate_", "minutes_", "spec_",
                       "chart_bar_", "chart_pie_", "banner_", "badge_", "poster_", "photo_"]:
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, names)
