import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.settings import resolve_sqlite_path

SQLITE = "django.db.backends.sqlite3"


class SqlitePathTests(SimpleTestCase):
    def test_relative_path_is_resolved_against_backend_dir(self):
        config = resolve_sqlite_path({"ENGINE": SQLITE, "NAME": "db.sqlite3"}, Path("/srv/app"))
        self.assertEqual(config["NAME"], "/srv/app/db.sqlite3")

    def test_absolute_path_and_memory_are_left_alone(self):
        for name in ["/data/vault.sqlite3", ":memory:"]:
            with self.subTest(name=name):
                config = resolve_sqlite_path({"ENGINE": SQLITE, "NAME": name}, Path("/srv/app"))
                self.assertEqual(config["NAME"], name)

    def test_other_databases_are_left_alone(self):
        config = {"ENGINE": "django.db.backends.postgresql", "NAME": "vault"}
        self.assertEqual(resolve_sqlite_path(config, Path("/srv/app"))["NAME"], "vault")

    def test_running_from_another_folder_uses_the_same_db(self):
        """The real bug: starting Django from a different working directory."""
        env = {**os.environ, "DATABASE_URL": "sqlite:///db.sqlite3", "DJANGO_SETTINGS_MODULE": "config.settings",
               "PYTHONPATH": str(settings.BASE_DIR)}
        code = "import django; django.setup(); from django.conf import settings as s; print(s.DATABASES['default']['NAME'])"
        with tempfile.TemporaryDirectory() as elsewhere:
            result = subprocess.run([sys.executable, "-c", code], cwd=elsewhere, env=env,
                                    capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), str(settings.BASE_DIR / "db.sqlite3"))
