"""
Tests for backend/decrypt_tool.py (Phase 7).

End-to-end: seed (--count 4) -> export ZIP through the API -> unzip -> run the
tool as a real subprocess, without Django in its environment, like a mentor would.
"""

import ast
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

import decrypt_tool

from .models import FileRecord
from .tests import TempStorageMixin

TOOL = Path(settings.BASE_DIR) / "decrypt_tool.py"


class DecryptToolTestCase(TempStorageMixin, TestCase):
    def setUp(self):
        super().setUp()
        admin = get_user_model().objects.create_superuser("boss", "boss@example.com")
        call_command("seed_files", "--count", "4", stdout=io.StringIO())
        self.records = {r.stored_name: r for r in FileRecord.objects.all()}

        # Export through the real API, then unzip like the mentor would.
        client = APIClient()
        client.force_authenticate(admin)
        response = client.get("/api/files/export/")
        zip_bytes = b"".join(response.streaming_content)
        response.close()

        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.export_dir = self.work / "vault-export"
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            archive.extractall(self.export_dir)
        self.out = self.work / "decrypted"

    def run_tool(self, *args, key=settings.FERNET_KEY):
        """Run decrypt_tool.py as a separate process, with no Django settings around."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO")}
        env.pop("FERNET_KEY", None)
        env["PYTHONIOENCODING"] = "utf-8"
        if key is not None:
            env["FERNET_KEY"] = key
        result = subprocess.run(
            [sys.executable, "-I", str(TOOL), *args], cwd=self.work, env=env,
            capture_output=True, text=True, encoding="utf-8",
        )
        self.output = result.stdout + result.stderr
        return result.returncode

    def manifest(self):
        return json.loads((self.export_dir / "manifest.json").read_text(encoding="utf-8"))

    def write_manifest(self, manifest):
        (self.export_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def out_files(self):
        return sorted(p.name for p in self.out.iterdir()) if self.out.exists() else []

    def everything_under_work(self):
        return sorted(str(p.relative_to(self.work)) for p in self.work.rglob("*"))


class EndToEndTests(DecryptToolTestCase):
    def test_export_unzip_decrypt_all_verified(self):
        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 0, self.output)
        self.assertEqual(self.output.count("✓ verified"), 4)
        self.assertIn("Summary: 4 ok, 0 failed, 0 missing", self.output)
        self.assertEqual(self.out_files(), sorted(r.original_name for r in self.records.values()))
        for record in self.records.values():
            data = (self.out / record.original_name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), record.sha256)

    def test_default_output_folder_is_decrypted(self):
        code = self.run_tool(str(self.export_dir))

        self.assertEqual(code, 0, self.output)
        self.assertEqual(len(list((self.work / "decrypted").iterdir())), 4)

    def test_never_overwrites_second_run_adds_numbered_copies(self):
        self.run_tool(str(self.export_dir), "--out", str(self.out))
        first = {name: (self.out / name).read_bytes() for name in self.out_files()}
        (self.out / sorted(first)[0]).write_bytes(b"user edited this")  # must survive

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 0, self.output)
        self.assertEqual(len(self.out_files()), 8)
        self.assertEqual((self.out / sorted(first)[0]).read_bytes(), b"user edited this")
        for name in first:
            stem, ext = os.path.splitext(name)
            self.assertTrue((self.out / f"{stem} (1){ext}").exists())

    def test_key_file_with_plain_key_or_env_line(self):
        for content in [settings.FERNET_KEY + "\n", f"DEBUG=True\nFERNET_KEY={settings.FERNET_KEY}\n"]:
            with self.subTest(content=content.split("=")[0]):
                key_file = self.work / "key.txt"
                key_file.write_text(content)
                out = self.work / f"out-{len(content)}"

                code = self.run_tool(str(self.export_dir), "--key-file", str(key_file), "--out", str(out), key=None)

                self.assertEqual(code, 0, self.output)

    def test_single_enc_file_uses_manifest_next_to_it(self):
        record = next(iter(self.records.values()))

        code = self.run_tool(str(self.export_dir / record.stored_name), "--out", str(self.out))

        self.assertEqual(code, 0, self.output)
        self.assertEqual(self.out_files(), [record.original_name])
        self.assertIn("✓ verified", self.output)

    def test_without_manifest_uses_magic_bytes_for_extension(self):
        (self.export_dir / "manifest.json").unlink()

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 0, self.output)
        self.assertIn("sha256 not checked", self.output)
        expected = sorted(
            r.stored_name[:-4] + {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}[r.mime_type]
            for r in self.records.values()
        )
        self.assertEqual(self.out_files(), expected)


class FailureTests(DecryptToolTestCase):
    def test_wrong_key_reports_each_file_and_writes_nothing(self):
        code = self.run_tool(str(self.export_dir), "--out", str(self.out), key=Fernet.generate_key().decode())

        self.assertEqual(code, 1)
        self.assertEqual(self.output.count("wrong key, or the .enc file was modified"), 4)
        self.assertIn("Summary: 0 ok, 4 failed, 0 missing", self.output)
        self.assertEqual(self.out_files(), [])

    def test_tampered_file_fails_others_still_decrypted(self):
        victim = sorted(self.records)[0]
        path = self.export_dir / victim
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0x01
        path.write_bytes(bytes(data))

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 1)
        self.assertIn(f"✗ FAILED     {self.records[victim].original_name}", self.output)
        self.assertIn("Summary: 3 ok, 1 failed, 0 missing", self.output)
        self.assertNotIn(self.records[victim].original_name, self.out_files())
        self.assertEqual(len(self.out_files()), 3)

    def test_sha256_mismatch_is_reported_and_not_written(self):
        manifest = self.manifest()
        manifest["files"][0]["sha256"] = "0" * 64
        self.write_manifest(manifest)

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 1)
        self.assertIn(f"✗ MISMATCH   {manifest['files'][0]['original_name']}", self.output)
        self.assertIn("Summary: 3 ok, 1 failed, 0 missing", self.output)
        self.assertEqual(len(self.out_files()), 3)

    def test_missing_enc_file_is_counted(self):
        (self.export_dir / sorted(self.records)[0]).unlink()

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 1)
        self.assertIn("Summary: 3 ok, 0 failed, 1 missing", self.output)

    def test_no_key_exits_2_with_clear_message(self):
        code = self.run_tool(str(self.export_dir), key=None)

        self.assertEqual(code, 2)
        self.assertIn("Set the FERNET_KEY environment variable or use --key-file", self.output)

    def test_invalid_key_exits_2_without_printing_it(self):
        code = self.run_tool(str(self.export_dir), key="definitely-not-a-key")

        self.assertEqual(code, 2)
        self.assertIn("not a valid Fernet key", self.output)
        self.assertNotIn("definitely-not-a-key", self.output)

    def test_key_on_command_line_is_refused_and_not_echoed(self):
        for args in (["--key", settings.FERNET_KEY], [f"--key={settings.FERNET_KEY}"]):
            with self.subTest(form=args[0][:5]):
                code = self.run_tool(str(self.export_dir), *args, key=None)

                self.assertEqual(code, 2)
                self.assertIn("Refusing --key", self.output)
                self.assertNotIn(settings.FERNET_KEY, self.output)
                self.assertEqual(self.out_files(), [])

    def test_broken_manifest_exits_2(self):
        (self.export_dir / "manifest.json").write_text("{not json")

        self.assertEqual(self.run_tool(str(self.export_dir)), 2)
        self.assertIn("manifest.json is not valid", self.output)


class MaliciousManifestTests(DecryptToolTestCase):
    def test_path_traversal_names_stay_inside_out(self):
        manifest = self.manifest()
        evil_names = ["../../evil.pdf", "/etc/cron.d/evil.png", "..\\..\\windows.jpg", "sub/dir/x.pdf"]
        for entry, evil in zip(manifest["files"], evil_names):
            entry["original_name"] = evil
        self.write_manifest(manifest)
        before = set(self.everything_under_work())

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 0, self.output)
        self.assertEqual(self.out_files(), sorted(["evil.pdf", "evil.png", "windows.jpg", "x.pdf"]))
        created = set(self.everything_under_work()) - before
        self.assertTrue(all(p.startswith("decrypted") for p in created), created)
        self.assertFalse((self.work.parent / "evil.pdf").exists())

    def test_stored_name_traversal_is_refused(self):
        secret = self.work / "secret.txt"
        secret.write_text("outside the export folder")
        manifest = self.manifest()
        manifest["files"][0]["stored_name"] = "../secret.txt"
        self.write_manifest(manifest)

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 1)
        self.assertIn("invalid stored_name '../secret.txt' in manifest", self.output)

    def test_duplicate_original_names_get_numbered(self):
        manifest = self.manifest()
        for entry in manifest["files"][:2]:  # two different PDFs/images, same name
            entry["original_name"] = "report.pdf"
        self.write_manifest(manifest)

        code = self.run_tool(str(self.export_dir), "--out", str(self.out))

        self.assertEqual(code, 0, self.output)
        self.assertIn("report.pdf", self.out_files())
        self.assertIn("report (1).pdf", self.out_files())


class WriteErrorTests(DecryptToolTestCase):
    def test_unwritable_output_fails_that_file_and_keeps_going(self):
        """e.g. disk full on one file: report it, continue with the rest, exit 1."""
        blocked = sorted(r.original_name for r in self.records.values())[0]
        real_write = decrypt_tool.write_new_file

        def write_or_fail(out_dir, name, data):
            if name == blocked:
                raise OSError(28, "No space left on device")
            return real_write(out_dir, name, data)

        self.out.mkdir()
        output = io.StringIO()
        with mock.patch.object(decrypt_tool, "write_new_file", side_effect=write_or_fail), \
                mock.patch.dict(os.environ, {"FERNET_KEY": settings.FERNET_KEY}), \
                contextlib.redirect_stdout(output):
            code = decrypt_tool.run([str(self.export_dir), "--out", str(self.out)])

        self.assertEqual(code, 1)
        self.assertIn("could not write output", output.getvalue())
        self.assertIn("3 ok, 1 failed", output.getvalue())
        self.assertEqual(len(self.out_files()), 3)
        self.assertNotIn(blocked, self.out_files())


class SafeFilenameTests(SimpleTestCase):
    """Unit tests for the name cleaning (covers Windows rules we can't run here)."""

    def check(self, raw, expected):
        self.assertEqual(decrypt_tool.safe_filename(raw, "fallback.bin"), expected)

    def test_folders_are_dropped(self):
        self.check("../../a.pdf", "a.pdf")
        self.check("C:\\Users\\x\\b.pdf", "b.pdf")

    def test_windows_forbidden_characters_removed(self):
        self.check('re<po>rt:"v2"|?*.pdf', "reportv2.pdf")

    def test_windows_reserved_names_prefixed(self):
        for name in ["CON.pdf", "nul.png", "COM1.jpg", "lpt9.pdf"]:
            with self.subTest(name=name):
                self.check(name, "_" + name)

    def test_control_chars_and_dots_stripped(self):
        self.check("bad\nname\u202e.pdf", "badname.pdf")
        self.check(".hidden.pdf", "hidden.pdf")
        self.check("trailing. . ", "trailing")

    def test_empty_falls_back(self):
        for name in ["", "..", "/", "\x00", "..."]:
            with self.subTest(name=name):
                self.check(name, "fallback.bin")

    def test_long_names_keep_extension(self):
        result = decrypt_tool.safe_filename("a" * 500 + ".pdf", "x")
        self.assertEqual(len(result), decrypt_tool.MAX_NAME)
        self.assertTrue(result.endswith(".pdf"))


class StandaloneTests(SimpleTestCase):
    def test_imports_only_stdlib_and_cryptography(self):
        tree = ast.parse(TOOL.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module.split(".")[0])

        third_party = modules - set(sys.stdlib_module_names)
        self.assertEqual(third_party, {"cryptography"})
