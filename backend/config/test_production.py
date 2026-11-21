"""Production setup: Django serves the React build, /api/ stays JSON, deploy checks pass."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

BACKEND_DIR = Path(__file__).resolve().parent.parent
INDEX_HTML = '<!doctype html><div id="root"></div><script src="/static/assets/index-abc123.js"></script>'


class FrontendRoutingTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dist = Path(temp.name)
        (self.dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
        override = override_settings(FRONTEND_DIST=self.dist)
        override.enable()
        self.addCleanup(override.disable)

    def test_react_routes_get_index_html(self):
        for url in ["/", "/login", "/register", "/some/deep/page", "/?search=x&page=2", "/apiary"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<div id="root">')
                self.assertEqual(response["Cache-Control"], "no-cache")

    def assertJson404(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"detail": "Not found."})

    def test_api_404s_stay_json(self):
        for url in ["/api/", "/api/nope/", "/api/files/nope/extra/", "/api/auth/unknown/"]:
            with self.subTest(url=url):
                self.assertJson404(self.client.get(url))

    def test_api_404s_are_json_for_any_method_without_csrf_page(self):
        self.assertJson404(self.client.post("/api/nope/", {"a": 1}))
        self.assertJson404(self.client.delete("/api/nope/"))

    @override_settings(DEBUG=True)
    def test_api_404s_are_json_in_debug_mode_too(self):
        # With DEBUG=True Django ignores handler404 and shows its HTML debug page;
        # the api/ catch-all route avoids that.
        self.assertJson404(self.client.get("/api/nope/"))

    def test_api_without_trailing_slash_redirects_then_404s_as_json(self):
        response = self.client.get("/api/nope", follow=True)
        self.assertEqual(response.redirect_chain, [("/api/nope/", 301)])
        self.assertJson404(response)
        # Real endpoints keep working without the slash, via the same redirect.
        self.assertEqual(self.client.get("/api/files")["Location"], "/api/files/")

    def test_api_404_for_missing_file_is_json_too(self):
        user = get_user_model().objects.create_user("alice")
        response = self.client.get(
            "/api/files/999999/", HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_admin_and_static_are_not_swallowed(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)  # to the admin login page
        self.assertIn("/admin/login/", response["Location"])

        response = self.client.get("/static/does-not-exist.js")
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, '<div id="root">', status_code=404)

    def test_post_to_a_react_route_is_refused(self):
        self.assertEqual(self.client.post("/login").status_code, 405)

    def test_clear_message_when_frontend_is_not_built(self):
        (self.dist / "index.html").unlink()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "npm run build", status_code=503)


class DeployCheckTests(TestCase):
    def test_check_deploy_passes_with_production_env(self):
        """`manage.py check --deploy` has no warnings with the env from DEPLOY.md."""
        env = {
            **os.environ,
            "DEBUG": "False",
            "SECRET_KEY": "x" * 20 + "-deploy-test-only-" + "y" * 30,  # long, not "django-insecure-"
            "FERNET_KEY": Fernet.generate_key().decode(),
            "ALLOWED_HOSTS": "demo.pythonanywhere.com",
            "CSRF_TRUSTED_ORIGINS": "https://demo.pythonanywhere.com",
            "NUM_PROXIES": "1",
        }
        env.pop("SECURE_HSTS_SECONDS", None)
        env.pop("SECURE_SSL_REDIRECT", None)
        result = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
            cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no issues", result.stdout + result.stderr)
