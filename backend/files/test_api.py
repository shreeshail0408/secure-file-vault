"""API tests for /api/files/ (Phase 4)."""

import hashlib
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from .crypto import decrypt_bytes
from .models import FileRecord
from .storage import save_encrypted
from .tests import TempStorageMixin, make_pdf_bytes, make_png_bytes

User = get_user_model()
FILES_URL = "/api/files/"
MB = 1024 * 1024


def make_jpg_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color=(10, 120, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


def detail_url(file_id, action=""):
    return f"{FILES_URL}{file_id}/" + (f"{action}/" if action else "")


def upload(name, data):
    return SimpleUploadedFile(name, data, content_type="application/octet-stream")


class FileAPITestCase(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        # No passwords: these tests log in with force_authenticate (JWT login is
        # tested in accounts/), and skipping password hashing keeps the suite fast.
        self.alice = User.objects.create_user("alice", "alice@example.com")
        self.bob = User.objects.create_user("bob", "bob@example.com")
        self.admin = User.objects.create_user("admin", "admin@example.com", is_staff=True)
        self.client = APIClient()

    def login(self, user):
        self.client.force_authenticate(user)

    def make_record(self, owner, name="report.pdf", data=None, file_type="pdf", mime="application/pdf"):
        """Create a file directly in the DB + storage (no API call)."""
        data = data if data is not None else make_pdf_bytes()
        return FileRecord.objects.create(
            original_name=name, file_type=file_type, mime_type=mime, size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            stored_name=save_encrypted(data), uploaded_by=owner,
        )

    def enc_path(self, record):
        record.refresh_from_db()
        return self.storage_dir / record.stored_name

    def post_file(self, name, data):
        return self.client.post(FILES_URL, {"file": upload(name, data)}, format="multipart")

    def put_replace(self, record, name, data):
        return self.client.put(
            detail_url(record.id, "replace"), {"file": upload(name, data)}, format="multipart"
        )


# --- Authentication ---------------------------------------------------------

class AuthRequiredTests(FileAPITestCase):
    def test_every_endpoint_needs_a_token(self):
        record = self.make_record(self.alice)
        requests = [
            ("get", FILES_URL), ("post", FILES_URL),
            ("get", detail_url(record.id)), ("patch", detail_url(record.id)),
            ("delete", detail_url(record.id)), ("put", detail_url(record.id, "replace")),
            ("get", detail_url(record.id, "preview")), ("get", detail_url(record.id, "download")),
        ]
        for method, url in requests:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 401)


# --- Upload -----------------------------------------------------------------

class UploadTests(FileAPITestCase):
    def setUp(self):
        super().setUp()
        self.login(self.alice)

    def test_upload_pdf(self):
        pdf = make_pdf_bytes()

        response = self.post_file("report.pdf", pdf)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["original_name"], "report.pdf")
        self.assertEqual(response.data["file_type"], "pdf")
        self.assertEqual(response.data["mime_type"], "application/pdf")
        self.assertEqual(response.data["size"], len(pdf))
        self.assertEqual(response.data["uploaded_by"], "alice")
        self.assertTrue(response.data["can_edit"])
        record = FileRecord.objects.get(id=response.data["id"])
        self.assertEqual(decrypt_bytes(self.enc_path(record).read_bytes()), pdf)
        self.assertEqual(record.sha256, hashlib.sha256(pdf).hexdigest())  # of the plaintext

    def test_upload_png_and_jpg(self):
        for name, data, mime in [
            ("photo.png", make_png_bytes(), "image/png"),
            ("photo.jpg", make_jpg_bytes(), "image/jpeg"),
            ("photo.JPEG", make_jpg_bytes(), "image/jpeg"),
        ]:
            with self.subTest(name=name):
                response = self.post_file(name, data)
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.data["file_type"], "image")
                self.assertEqual(response.data["mime_type"], mime)

    def test_fake_pdf_rejected_by_magic_bytes(self):
        response = self.post_file("invoice.pdf", b"MZ\x90\x00 this is really an .exe")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only PDF, PNG and JPG", str(response.data["file"]))
        self.assertEqual(self.stored_files(), [])

    def test_extension_must_match_content(self):
        response = self.post_file("photo.pdf", make_png_bytes())

        self.assertEqual(response.status_code, 400)
        self.assertIn("doesn't match its content", str(response.data["file"]))

    def test_valid_content_with_dangerous_extension_rejected(self):
        response = self.post_file("report.exe", make_pdf_bytes())

        self.assertEqual(response.status_code, 400)

    def test_empty_file_rejected(self):
        response = self.post_file("empty.pdf", b"")

        self.assertEqual(response.status_code, 400)
        self.assertIn("empty", str(response.data["file"]))

    def test_missing_file_field_rejected(self):
        response = self.client.post(FILES_URL, {}, format="multipart")

        self.assertEqual(response.status_code, 400)

    def test_just_over_10mb_rejected_before_encrypting(self):
        too_big = b"%PDF-" + b"0" * (10 * MB - 4)  # 10 MB + 1 byte
        with mock.patch("files.views.save_encrypted") as save:
            response = self.post_file("big.pdf", too_big)

        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", str(response.data["file"]))
        save.assert_not_called()

    def test_much_bigger_than_10mb_rejected(self):
        response = self.post_file("huge.pdf", b"%PDF-" + b"0" * (12 * MB))

        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", str(response.data["file"]))
        self.assertEqual(self.stored_files(), [])

    def test_exactly_10mb_accepted(self):
        response = self.post_file("max.pdf", b"%PDF-" + b"0" * (10 * MB - 5))

        self.assertEqual(response.status_code, 201)

    def test_large_upload_never_spills_plaintext_to_a_temp_file(self):
        """Django's default handler writes uploads > 2.5 MB to /tmp. Ours must not."""
        data = b"%PDF-" + b"0" * (3 * MB)
        with mock.patch(
            "django.core.files.uploadhandler.TemporaryFileUploadHandler.new_file",
            side_effect=AssertionError("plaintext was written to a temp file"),
        ):
            response = self.post_file("three-mb.pdf", data)

        self.assertEqual(response.status_code, 201)

    def test_upload_name_path_parts_stripped(self):
        response = self.post_file("..\\..\\etc\\report.pdf", make_pdf_bytes())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["original_name"], "report.pdf")


# --- List, search, filter, details -----------------------------------------

class ListTests(FileAPITestCase):
    def setUp(self):
        super().setUp()
        self.alice_pdf = self.make_record(self.alice, "Quarterly Report.pdf")
        self.bob_png = self.make_record(
            self.bob, "holiday.png", make_png_bytes(), "image", "image/png"
        )

    def names(self, response):
        return sorted(f["original_name"] for f in response.data["results"])

    def test_every_user_sees_every_file_with_correct_can_edit(self):
        self.login(self.bob)

        response = self.client.get(FILES_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        can_edit = {f["original_name"]: f["can_edit"] for f in response.data["results"]}
        self.assertEqual(can_edit, {"Quarterly Report.pdf": False, "holiday.png": True})

    def test_admin_can_edit_everything(self):
        self.login(self.admin)

        results = self.client.get(FILES_URL).data["results"]

        self.assertTrue(all(f["can_edit"] for f in results))

    def test_search_by_name_is_case_insensitive(self):
        self.login(self.alice)

        self.assertEqual(self.names(self.client.get(FILES_URL, {"search": "QUARTER"})),
                         ["Quarterly Report.pdf"])
        self.assertEqual(self.names(self.client.get(FILES_URL, {"search": "nothing"})), [])

    def test_filter_by_type(self):
        self.login(self.alice)

        self.assertEqual(self.names(self.client.get(FILES_URL, {"type": "pdf"})),
                         ["Quarterly Report.pdf"])
        self.assertEqual(self.names(self.client.get(FILES_URL, {"type": "image"})),
                         ["holiday.png"])

    def test_invalid_type_filter_returns_400(self):
        self.login(self.alice)

        self.assertEqual(self.client.get(FILES_URL, {"type": "exe"}).status_code, 400)

    def test_stored_name_never_exposed(self):
        self.login(self.alice)
        responses = [
            self.client.get(FILES_URL),
            self.client.get(detail_url(self.alice_pdf.id)),
            self.post_file("new.pdf", make_pdf_bytes()),
            self.client.patch(detail_url(self.alice_pdf.id), {"original_name": "x"}),
        ]
        for response in responses:
            body = response.content.decode()
            self.assertNotIn("stored_name", body)
            self.assertNotIn(".enc", body)

    def test_detail_fields(self):
        self.login(self.alice)

        response = self.client.get(detail_url(self.alice_pdf.id))

        self.assertEqual(set(response.data), {
            "id", "original_name", "file_type", "mime_type", "size",
            "uploaded_by", "can_edit", "created_at", "updated_at",
        })


# --- 404s -------------------------------------------------------------------

class NotFoundTests(FileAPITestCase):
    def test_unknown_or_malformed_id_returns_404(self):
        self.login(self.admin)
        for file_id in ["99999", "abc"]:
            for method, url in [
                ("get", detail_url(file_id)),
                ("patch", detail_url(file_id)),
                ("delete", detail_url(file_id)),
                ("put", detail_url(file_id, "replace")),
                ("get", detail_url(file_id, "preview")),
                ("get", detail_url(file_id, "download")),
            ]:
                with self.subTest(method=method, url=url):
                    self.assertEqual(getattr(self.client, method)(url).status_code, 404)


# --- Preview / download -----------------------------------------------------

class PreviewDownloadTests(FileAPITestCase):
    def setUp(self):
        super().setUp()
        self.pdf = make_pdf_bytes()
        self.record = self.make_record(self.alice, "report.pdf", self.pdf)

    def test_preview_is_inline_with_correct_content_type(self):
        self.login(self.alice)

        response = self.client.get(detail_url(self.record.id, "preview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["Content-Disposition"], 'inline; filename="report.pdf"')
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response.content, self.pdf)

    def test_download_is_attachment(self):
        self.login(self.alice)

        response = self.client.get(detail_url(self.record.id, "download"))

        self.assertEqual(response["Content-Disposition"], 'attachment; filename="report.pdf"')
        self.assertEqual(response.content, self.pdf)

    def test_image_preview_content_type(self):
        png = make_png_bytes()
        record = self.make_record(self.alice, "pic.png", png, "image", "image/png")
        self.login(self.alice)

        response = self.client.get(detail_url(record.id, "preview"))

        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response.content, png)

    def test_other_users_can_preview_and_download(self):
        self.login(self.bob)

        for action in ("preview", "download"):
            with self.subTest(action=action):
                response = self.client.get(detail_url(self.record.id, action))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, self.pdf)

    def test_tampered_file_returns_json_500(self):
        path = self.enc_path(self.record)
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0x01  # flip one bit
        path.write_bytes(bytes(data))
        self.login(self.alice)

        with self.assertLogs("files.views", level="ERROR"):
            response = self.client.get(detail_url(self.record.id, "download"))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            {"detail": "Could not decrypt file: it was modified or encrypted with a different key."},
        )
        self.assertNotIn("Traceback", response.content.decode())

    def test_missing_enc_file_returns_json_500(self):
        self.enc_path(self.record).unlink()
        self.login(self.alice)

        with self.assertLogs("files.views", level="ERROR"):
            response = self.client.get(detail_url(self.record.id, "preview"))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "The stored file is missing on the server."})


class ContentDispositionTests(FileAPITestCase):
    """Names stored in the DB (e.g. via admin or seed) must not break headers."""

    def header_for(self, name):
        record = self.make_record(self.alice, name)
        self.login(self.alice)
        return self.client.get(detail_url(record.id, "download"))["Content-Disposition"]

    def test_quotes_are_escaped(self):
        self.assertEqual(self.header_for('my "best" report.pdf'),
                         r'attachment; filename="my \"best\" report.pdf"')

    def test_newlines_cannot_inject_headers(self):
        header = self.header_for("evil\r\nSet-Cookie: x=1.pdf")

        self.assertNotIn("\r", header)
        self.assertNotIn("\n", header)
        self.assertEqual(header, "attachment; filename*=utf-8''evil%0D%0ASet-Cookie%3A%20x%3D1.pdf")

    def test_non_ascii_uses_filename_star(self):
        self.assertEqual(self.header_for("résumé.pdf"),
                         "attachment; filename*=utf-8''r%C3%A9sum%C3%A9.pdf")


# --- Rename -----------------------------------------------------------------

class RenameTests(FileAPITestCase):
    def setUp(self):
        super().setUp()
        self.record = self.make_record(self.alice, "report.pdf")

    def rename(self, new_name):
        return self.client.patch(detail_url(self.record.id), {"original_name": new_name}, format="json")

    def assert_renamed(self, given, expected):
        response = self.rename(given)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["original_name"], expected)
        self.record.refresh_from_db()
        self.assertEqual(self.record.original_name, expected)

    def test_owner_can_rename(self):
        self.login(self.alice)
        self.assert_renamed("Q4 summary.pdf", "Q4 summary.pdf")

    def test_extension_cannot_be_changed(self):
        self.login(self.alice)
        self.assert_renamed("hack.exe", "hack.pdf")

    def test_name_without_extension_gets_original_one(self):
        self.login(self.alice)
        self.assert_renamed("notes", "notes.pdf")

    def test_path_parts_are_stripped(self):
        self.login(self.alice)
        self.assert_renamed("../../etc/passwd", "passwd.pdf")
        self.assert_renamed("C:\\Windows\\evil.pdf", "evil.pdf")

    def test_control_characters_are_stripped(self):
        self.login(self.alice)
        # \n newline, \r, \t, \x1b escape, \u202e right-to-left override
        self.assert_renamed("bad\n\r\tna\x1bme\u202e.pdf", "badname.pdf")

    def test_nul_character_rejected(self):
        # DRF's CharField refuses NUL outright (400), before our cleaning runs.
        self.login(self.alice)

        self.assertEqual(self.rename("bad\x00name.pdf").status_code, 400)

    def test_empty_names_rejected(self):
        self.login(self.alice)
        for bad in ["", "   ", "..", ".pdf", ".PDF", "/", "\x01\x02", "\u202e"]:
            with self.subTest(bad=bad):
                self.assertEqual(self.rename(bad).status_code, 400)
        self.record.refresh_from_db()
        self.assertEqual(self.record.original_name, "report.pdf")

    def test_max_255_characters(self):
        self.login(self.alice)
        self.assert_renamed("a" * 251, "a" * 251 + ".pdf")  # exactly 255

        response = self.rename("a" * 252)  # 256 with ".pdf"
        self.assertEqual(response.status_code, 400)
        self.assertIn("too long", str(response.data["original_name"]))

    def test_other_user_cannot_rename(self):
        self.login(self.bob)

        response = self.rename("mine-now.pdf")

        self.assertEqual(response.status_code, 403)
        self.record.refresh_from_db()
        self.assertEqual(self.record.original_name, "report.pdf")

    def test_admin_can_rename_anyones_file(self):
        self.login(self.admin)
        self.assert_renamed("checked by admin.pdf", "checked by admin.pdf")

    def test_put_on_detail_not_allowed(self):
        self.login(self.alice)

        response = self.client.put(detail_url(self.record.id), {"original_name": "x"})

        self.assertEqual(response.status_code, 405)


# --- Replace ----------------------------------------------------------------

class ReplaceTests(FileAPITestCase):
    def setUp(self):
        super().setUp()
        self.old_pdf = make_pdf_bytes()
        self.record = self.make_record(self.alice, "report.pdf", self.old_pdf)
        self.old_path = self.enc_path(self.record)

    def test_owner_can_replace_with_same_type(self):
        new_pdf = make_pdf_bytes() + b"\n% new version"
        self.login(self.alice)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.put_replace(self.record, "v2.pdf", new_pdf)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["original_name"], "report.pdf")  # name kept
        self.assertEqual(response.data["size"], len(new_pdf))
        new_path = self.enc_path(self.record)
        self.assertNotEqual(new_path, self.old_path)
        self.assertFalse(self.old_path.exists())  # old .enc cleaned up
        self.assertEqual(decrypt_bytes(new_path.read_bytes()), new_pdf)
        self.assertEqual(self.stored_files(), [new_path.name])
        self.record.refresh_from_db()
        self.assertEqual(self.record.sha256, hashlib.sha256(new_pdf).hexdigest())

    def test_png_replaced_by_jpg_updates_mime_and_extension(self):
        record = self.make_record(self.alice, "logo.png", make_png_bytes(), "image", "image/png")
        self.login(self.alice)

        response = self.put_replace(record, "logo.jpg", make_jpg_bytes())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["original_name"], "logo.jpg")
        self.assertEqual(response.data["mime_type"], "image/jpeg")

    def test_different_type_rejected(self):
        self.login(self.alice)

        response = self.put_replace(self.record, "pic.png", make_png_bytes())

        self.assertEqual(response.status_code, 400)
        self.assertIn("same type", str(response.data["file"]))
        self.assertEqual(self.enc_path(self.record), self.old_path)
        self.assertEqual(self.stored_files(), [self.old_path.name])  # no new .enc left

    def test_invalid_replacement_rejected(self):
        self.login(self.alice)

        response = self.put_replace(self.record, "fake.pdf", b"not a pdf")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(decrypt_bytes(self.old_path.read_bytes()), self.old_pdf)

    def test_other_user_cannot_replace(self):
        self.login(self.bob)

        response = self.put_replace(self.record, "evil.pdf", make_pdf_bytes() + b"% evil")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(decrypt_bytes(self.enc_path(self.record).read_bytes()), self.old_pdf)

    def test_admin_can_replace(self):
        self.login(self.admin)

        response = self.put_replace(self.record, "fixed.pdf", make_pdf_bytes() + b"% fixed")

        self.assertEqual(response.status_code, 200)


# --- Delete -----------------------------------------------------------------

class DeleteTests(FileAPITestCase):
    def setUp(self):
        super().setUp()
        self.record = self.make_record(self.alice, "report.pdf")
        self.path = self.enc_path(self.record)

    def delete(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.delete(detail_url(self.record.id))

    def test_user_b_cannot_delete_user_a_file(self):
        self.login(self.bob)

        response = self.delete()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"], "Only the uploader or an admin can change or delete this file."
        )
        self.assertTrue(FileRecord.objects.filter(id=self.record.id).exists())
        self.assertTrue(self.path.exists())

    def test_owner_can_delete(self):
        self.login(self.alice)

        response = self.delete()

        self.assertEqual(response.status_code, 204)
        self.assertFalse(FileRecord.objects.filter(id=self.record.id).exists())
        self.assertFalse(self.path.exists())

    def test_admin_can_delete_anyones_file(self):
        self.login(self.admin)

        self.assertEqual(self.delete().status_code, 204)
        self.assertFalse(self.path.exists())

    def test_ownerless_file_only_admin_can_change(self):
        orphan = self.make_record(owner=None, name="orphan.pdf")

        self.login(self.alice)
        self.assertFalse(self.client.get(detail_url(orphan.id)).data["can_edit"])
        self.assertEqual(self.client.delete(detail_url(orphan.id)).status_code, 403)

        self.login(self.admin)
        self.assertEqual(self.client.delete(detail_url(orphan.id)).status_code, 204)
