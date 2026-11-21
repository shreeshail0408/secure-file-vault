import io
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet, InvalidToken
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .crypto import DecryptionError, decrypt_bytes, encrypt_bytes
from .models import FileRecord
from .storage import delete_file, read_decrypted, save_encrypted

MARKER = "TOP-SECRET-MARKER-42"


def make_pdf_bytes():
    """A real 2-page PDF containing MARKER as plain text."""
    buffer = io.BytesIO()
    # pageCompression=0 keeps the text readable in the raw bytes, so the
    # "ciphertext doesn't contain the plaintext" check is meaningful.
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    for page in (1, 2):
        pdf.drawString(72, 750, f"{MARKER} page {page}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_png_bytes():
    """A real 64x64 PNG image."""
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(200, 30, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


class TempStorageMixin:
    """Point STORAGE_DIR at a fresh temp folder for every test."""

    def setUp(self):
        super().setUp()
        self.storage_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        override = override_settings(STORAGE_DIR=self.storage_dir)
        override.enable()
        self.addCleanup(override.disable)

    def stored_files(self):
        return sorted(p.name for p in self.storage_dir.iterdir())


class CryptoTests(TestCase):
    def test_round_trip(self):
        data = make_pdf_bytes()
        self.assertEqual(decrypt_bytes(encrypt_bytes(data)), data)

    def test_garbage_raises_clear_error_not_invalid_token(self):
        with self.assertRaises(DecryptionError) as ctx:
            decrypt_bytes(b"this is not a fernet token")

        self.assertNotIsInstance(ctx.exception, InvalidToken)
        self.assertIn("modified or encrypted with a different key", str(ctx.exception))
        # "from None": Fernet's internal traceback is not chained onto ours.
        self.assertTrue(ctx.exception.__suppress_context__)


class StorageTests(TempStorageMixin, TestCase):
    def test_pdf_round_trip(self):
        pdf = make_pdf_bytes()
        self.assertTrue(pdf.startswith(b"%PDF"))

        name = save_encrypted(pdf)

        self.assertEqual(read_decrypted(name), pdf)

    def test_png_round_trip(self):
        png = make_png_bytes()

        name = save_encrypted(png)
        decrypted = read_decrypted(name)

        self.assertEqual(decrypted, png)
        self.assertEqual(Image.open(io.BytesIO(decrypted)).size, (64, 64))

    def test_enc_file_does_not_contain_original_bytes(self):
        pdf = make_pdf_bytes()
        self.assertIn(MARKER.encode(), pdf)  # sanity: marker is in the plaintext

        name = save_encrypted(pdf)
        on_disk = (self.storage_dir / name).read_bytes()

        self.assertNotEqual(on_disk, pdf)
        self.assertNotIn(pdf, on_disk)
        self.assertNotIn(MARKER.encode(), on_disk)
        self.assertNotIn(b"%PDF", on_disk)

    def test_png_signature_not_on_disk(self):
        name = save_encrypted(make_png_bytes())

        self.assertNotIn(b"\x89PNG", (self.storage_dir / name).read_bytes())

    def test_tampered_file_raises_clear_error(self):
        name = save_encrypted(make_pdf_bytes())
        path = self.storage_dir / name
        data = bytearray(path.read_bytes())
        middle = len(data) // 2
        data[middle] = ord("A") if data[middle] != ord("A") else ord("B")  # flip one byte
        path.write_bytes(bytes(data))

        with self.assertRaises(DecryptionError):
            read_decrypted(name)

    def test_truncated_file_raises_clear_error(self):
        name = save_encrypted(make_pdf_bytes())
        path = self.storage_dir / name
        path.write_bytes(path.read_bytes()[:100])  # simulate a half-written file

        with self.assertRaises(DecryptionError):
            read_decrypted(name)

    def test_wrong_key_raises_clear_error(self):
        name = save_encrypted(make_png_bytes())

        with override_settings(FERNET_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(DecryptionError) as ctx:
                read_decrypted(name)

        self.assertIn("different key", str(ctx.exception))

    def test_stored_name_is_uuid_enc_only(self):
        name = save_encrypted(b"data")

        self.assertRegex(name, r"^[0-9a-f]{32}\.enc$")
        self.assertEqual(self.stored_files(), [name])  # no leftover .tmp

    def test_user_input_cannot_reach_the_filesystem(self):
        for bad in ["../../etc/passwd", "/etc/passwd", "report.pdf", "abc.enc", ""]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    read_decrypted(bad)
                with self.assertRaises(ValueError):
                    delete_file(bad)

    def test_temp_file_only_ever_holds_ciphertext(self):
        """Plaintext never touches disk, not even in the temp file before rename."""
        pdf = make_pdf_bytes()
        seen = {}
        real_replace = __import__("os").replace

        def spy_replace(src, dst):
            seen["temp_contents"] = Path(src).read_bytes()
            real_replace(src, dst)

        with mock.patch("files.storage.os.replace", side_effect=spy_replace):
            save_encrypted(pdf)

        self.assertNotIn(MARKER.encode(), seen["temp_contents"])
        self.assertEqual(decrypt_bytes(seen["temp_contents"]), pdf)

    def test_crash_during_write_leaves_no_files(self):
        with mock.patch("files.storage.os.replace", side_effect=OSError("disk died")):
            with self.assertRaises(OSError):
                save_encrypted(make_pdf_bytes())

        self.assertEqual(self.stored_files(), [])  # no .enc, no stray .tmp

    def test_delete_file_is_ok_if_already_gone(self):
        name = save_encrypted(b"data")
        delete_file(name)

        delete_file(name)  # second time: must not raise

        self.assertEqual(self.stored_files(), [])


class FileRecordTests(TempStorageMixin, TestCase):
    def make_record(self, owner=None):
        data = make_pdf_bytes()
        return FileRecord.objects.create(
            original_name="report.pdf",
            file_type=FileRecord.PDF,
            mime_type="application/pdf",
            size=len(data),
            stored_name=save_encrypted(data),
            uploaded_by=owner,
        )

    def test_deleting_record_removes_enc_file(self):
        record = self.make_record()
        path = self.storage_dir / record.stored_name
        self.assertTrue(path.exists())

        # Run on_commit callbacks (TestCase never really commits).
        with self.captureOnCommitCallbacks(execute=True):
            record.delete()

        self.assertFalse(path.exists())
        self.assertFalse(FileRecord.objects.exists())

    def test_bulk_delete_removes_enc_files(self):
        self.make_record()
        self.make_record()
        self.assertEqual(len(self.stored_files()), 2)

        with self.captureOnCommitCallbacks(execute=True):
            FileRecord.objects.all().delete()

        self.assertEqual(self.stored_files(), [])

    def test_deleting_record_whose_enc_is_missing_does_not_crash(self):
        record = self.make_record()
        (self.storage_dir / record.stored_name).unlink()

        with self.captureOnCommitCallbacks(execute=True):
            record.delete()

        self.assertFalse(FileRecord.objects.exists())

    def test_rolled_back_delete_keeps_enc_file(self):
        record = self.make_record()
        record_id = record.pk  # delete() sets record.pk to None, even if rolled back
        path = self.storage_dir / record.stored_name

        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    record.delete()
                    raise RuntimeError("something failed after the delete")
            except RuntimeError:
                pass

        self.assertTrue(path.exists())
        self.assertTrue(FileRecord.objects.filter(pk=record_id).exists())

    def test_deleting_uploader_keeps_file(self):
        owner = get_user_model().objects.create_user("alice", password="x")
        record = self.make_record(owner=owner)

        owner.delete()

        record.refresh_from_db()
        self.assertIsNone(record.uploaded_by)
        self.assertTrue((self.storage_dir / record.stored_name).exists())
