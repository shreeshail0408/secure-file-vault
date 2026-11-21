"""Tests for GET /api/files/export/ (Phase 5)."""

import base64
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from cryptography.fernet import Fernet
from django.conf import settings

from .export import build_export_zip
from .test_api import FileAPITestCase, make_jpg_bytes
from .tests import make_pdf_bytes, make_png_bytes

EXPORT_URL = "/api/files/export/"
FIXED_NOW = datetime(2026, 11, 21, 10, 30, tzinfo=dt_timezone.utc)


class ExportTestCase(FileAPITestCase):
    def setUp(self):
        super().setUp()
        self.pdf = make_pdf_bytes()
        self.png = make_png_bytes()
        self.jpg = make_jpg_bytes()
        self.records = [
            self.make_record(self.alice, "report.pdf", self.pdf),
            self.make_record(self.bob, "holiday.png", self.png, "image", "image/png"),
            self.make_record(None, "résumé photo.jpg", self.jpg, "image", "image/jpeg"),
        ]
        self.plaintexts = {r.stored_name: d for r, d in zip(self.records, [self.pdf, self.png, self.jpg])}

    def export(self, user=None):
        if user:
            self.login(user)
        with mock.patch("files.export.timezone.now", return_value=FIXED_NOW):
            response = self.client.get(EXPORT_URL)
        if response.status_code == 200:
            self.zip_bytes = b"".join(response.streaming_content)
            response.close()
        return response

    def open_zip(self):
        return zipfile.ZipFile(io.BytesIO(self.zip_bytes))

    def manifest(self):
        with self.open_zip() as archive:
            return json.loads(archive.read("manifest.json"))


class ExportPermissionTests(ExportTestCase):
    def test_no_token_returns_401(self):
        self.assertEqual(self.export().status_code, 401)

    def test_non_admin_returns_403(self):
        for user in (self.alice, self.bob):
            with self.subTest(user=user.username):
                self.assertEqual(self.export(user).status_code, 403)

    def test_admin_gets_zip(self):
        response = self.export(self.admin)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="vault-export-2026-11-21.zip"'
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(response.streaming)  # sent in chunks, not one big bytes object


class ExportContentTests(ExportTestCase):
    def test_zip_contains_enc_files_manifest_and_readme(self):
        self.export(self.admin)

        with self.open_zip() as archive:
            names = set(archive.namelist())

        expected = {r.stored_name for r in self.records} | {"manifest.json", "README.txt"}
        self.assertEqual(names, expected)

    def test_every_entry_uses_zip_stored(self):
        self.export(self.admin)

        with self.open_zip() as archive:
            for info in archive.infolist():
                with self.subTest(entry=info.filename):
                    self.assertEqual(info.compress_type, zipfile.ZIP_STORED)

    def test_enc_files_are_exactly_the_stored_ciphertext(self):
        self.export(self.admin)

        with self.open_zip() as archive:
            for record in self.records:
                with self.subTest(file=record.original_name):
                    in_zip = archive.read(record.stored_name)
                    self.assertEqual(in_zip, (self.storage_dir / record.stored_name).read_bytes())
                    self.assertNotEqual(in_zip, self.plaintexts[record.stored_name])

    def test_manifest_lists_each_file(self):
        self.export(self.admin)

        manifest = self.manifest()

        self.assertEqual(manifest["file_count"], 3)
        self.assertEqual(manifest["missing"], [])
        self.assertEqual(manifest["exported_at"], "2026-11-21T10:30:00+00:00")
        by_name = {f["stored_name"]: f for f in manifest["files"]}
        for record in self.records:
            plaintext = self.plaintexts[record.stored_name]
            self.assertEqual(by_name[record.stored_name], {
                "stored_name": record.stored_name,
                "original_name": record.original_name,
                "mime_type": record.mime_type,
                "size": len(plaintext),
                "sha256": hashlib.sha256(plaintext).hexdigest(),
            })

    def test_mentor_can_decrypt_and_verify_with_the_key(self):
        """What the mentor does offline: decrypt each .enc, compare with manifest sha256."""
        self.export(self.admin)
        fernet = Fernet(settings.FERNET_KEY)

        with self.open_zip() as archive:
            for entry in self.manifest()["files"]:
                decrypted = fernet.decrypt(archive.read(entry["stored_name"]))
                self.assertEqual(hashlib.sha256(decrypted).hexdigest(), entry["sha256"])
                self.assertEqual(len(decrypted), entry["size"])

    def test_readme_explains_decrypt_tool_and_missing_key(self):
        self.export(self.admin)

        with self.open_zip() as archive:
            readme = archive.read("README.txt").decode()

        self.assertIn("decrypt_tool.py", readme)
        self.assertIn("manifest.json", readme)
        self.assertIn("NOT in this archive", readme)
        self.assertIn("Files:    3", readme)

    def test_filters_in_query_string_are_ignored(self):
        self.login(self.admin)
        with mock.patch("files.export.timezone.now", return_value=FIXED_NOW):
            response = self.client.get(EXPORT_URL, {"type": "pdf", "search": "report"})
        self.zip_bytes = b"".join(response.streaming_content)
        response.close()

        self.assertEqual(self.manifest()["file_count"], 3)

    def test_empty_vault_exports_manifest_and_readme_only(self):
        for record in self.records:
            record.delete()

        self.export(self.admin)

        with self.open_zip() as archive:
            self.assertEqual(sorted(archive.namelist()), ["README.txt", "manifest.json"])
        self.assertEqual(self.manifest()["file_count"], 0)

    def test_missing_enc_is_reported_not_crashing(self):
        (self.storage_dir / self.records[1].stored_name).unlink()

        with self.assertLogs("files.export", level="WARNING"):
            response = self.export(self.admin)

        self.assertEqual(response.status_code, 200)
        manifest = self.manifest()
        self.assertEqual(manifest["file_count"], 2)
        self.assertEqual(manifest["missing"], ["holiday.png"])


class ExportSecurityTests(ExportTestCase):
    def test_fernet_key_is_never_in_the_zip(self):
        self.export(self.admin)
        key_text = settings.FERNET_KEY
        forbidden = {
            "FERNET_KEY (base64 text)": key_text.encode(),
            "FERNET_KEY (raw 32 bytes)": base64.urlsafe_b64decode(key_text),
            # The two 16-byte halves Fernet actually uses (signing / encryption keys)
            "signing key half": base64.urlsafe_b64decode(key_text)[:16],
            "encryption key half": base64.urlsafe_b64decode(key_text)[16:],
            "SECRET_KEY": settings.SECRET_KEY.encode(),
        }

        # 1) Every entry, one by one.
        with self.open_zip() as archive:
            for entry in archive.namelist():
                content = archive.read(entry)
                for label, secret in forbidden.items():
                    with self.subTest(entry=entry, secret=label):
                        self.assertNotIn(secret, content)
        # 2) The raw ZIP bytes (file names, headers, comments).
        for label, secret in forbidden.items():
            with self.subTest(entry="<whole zip>", secret=label):
                self.assertNotIn(secret, self.zip_bytes)

    def test_export_never_decrypts_anything(self):
        with mock.patch(
            "cryptography.fernet.Fernet.decrypt",
            side_effect=AssertionError("export must not decrypt"),
        ):
            response = self.export(self.admin)

        self.assertEqual(response.status_code, 200)

    def test_no_plaintext_in_zip(self):
        self.export(self.admin)

        for label, plaintext in [("pdf", self.pdf), ("png", self.png), ("jpg", self.jpg)]:
            with self.subTest(file=label):
                self.assertNotIn(plaintext, self.zip_bytes)
        self.assertNotIn(b"%PDF", self.zip_bytes)
        self.assertNotIn(b"\x89PNG", self.zip_bytes)

    def test_temp_zip_file_is_closed_after_response(self):
        created = []

        def spy(records):
            zip_file = build_export_zip(records)
            created.append(zip_file)
            return zip_file

        self.login(self.admin)
        with mock.patch("files.views.build_export_zip", side_effect=spy):
            response = self.client.get(EXPORT_URL)
        self.assertFalse(created[0].closed)  # still open while streaming

        b"".join(response.streaming_content)
        response.close()

        self.assertTrue(created[0].closed)  # TemporaryFile is deleted on close
