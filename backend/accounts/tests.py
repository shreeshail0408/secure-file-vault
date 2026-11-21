from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"
ME_URL = "/api/auth/me/"

STRONG_PASSWORD = "Vault-Tiger-2026!"

NO_THROTTLE = {"login": None, "register": None}


def register_payload(**overrides):
    data = {
        "username": "alice",
        "email": "alice@example.com",
        "password": STRONG_PASSWORD,
        "confirm_password": STRONG_PASSWORD,
    }
    data.update(overrides)
    return data


class AuthTestCase(APITestCase):
    def setUp(self):
        # Throttle counters live in the cache; start every test from zero.
        cache.clear()

    def assert_no_password(self, response):
        """The password and its hash must never appear in a response body."""
        body = response.content.decode()
        self.assertNotIn("password", body.lower())
        self.assertNotIn("pbkdf2", body)
        self.assertNotIn(STRONG_PASSWORD, body)


@override_settings(AUTH_THROTTLE_RATES=NO_THROTTLE)
class RegisterTests(AuthTestCase):
    def test_register_ok(self):
        response = self.client.post(REGISTER_URL, register_payload())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data,
            {"id": response.data["id"], "username": "alice",
             "email": "alice@example.com", "is_staff": False},
        )
        self.assert_no_password(response)
        user = User.objects.get(username="alice")
        self.assertTrue(user.check_password(STRONG_PASSWORD))  # stored hashed

    def test_duplicate_username_returns_400(self):
        self.client.post(REGISTER_URL, register_payload())
        response = self.client.post(
            REGISTER_URL, register_payload(username="ALICE", email="other@example.com")
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["username"], ["This username is already taken."])

    def test_duplicate_email_returns_400(self):
        self.client.post(REGISTER_URL, register_payload())
        response = self.client.post(
            REGISTER_URL, register_payload(username="bob", email="Alice@Example.com")
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["email"], ["An account with this email already exists."])

    def test_weak_password_returns_400(self):
        response = self.client.post(
            REGISTER_URL, register_payload(password="12345", confirm_password="12345")
        )

        self.assertEqual(response.status_code, 400)
        messages = " ".join(response.data["password"])
        self.assertIn("too short", messages)
        self.assertIn("entirely numeric", messages)
        self.assertFalse(User.objects.exists())

    def test_password_mismatch_returns_400(self):
        response = self.client.post(
            REGISTER_URL, register_payload(confirm_password="Something-Else-99")
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("confirm_password", response.data)

    def test_register_ignores_a_stale_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-garbage")

        response = self.client.post(REGISTER_URL, register_payload())

        self.assertEqual(response.status_code, 201)

    def test_login_ignores_a_stale_token(self):
        User.objects.create_user("bob", "bob@example.com", STRONG_PASSWORD)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-garbage")

        response = self.client.post(LOGIN_URL, {"username": "bob", "password": STRONG_PASSWORD})

        self.assertEqual(response.status_code, 200)

    def test_cannot_register_as_staff_or_superuser(self):
        response = self.client.post(
            REGISTER_URL,
            register_payload(is_staff=True, is_superuser=True),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["is_staff"])
        user = User.objects.get(username="alice")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


@override_settings(AUTH_THROTTLE_RATES=NO_THROTTLE)
class LoginAndTokenTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        User.objects.create_user("alice", "alice@example.com", STRONG_PASSWORD)

    def login(self, password=STRONG_PASSWORD):
        return self.client.post(LOGIN_URL, {"username": "alice", "password": password})

    def test_login_ok(self):
        response = self.login()

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assert_no_password(response)

    def test_wrong_password_returns_401(self):
        response = self.login(password="wrong-password")

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_refresh_gives_working_access_token(self):
        refresh = self.login().data["refresh"]

        response = self.client.post(REFRESH_URL, {"refresh": refresh})
        self.assertEqual(response.status_code, 200)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get(ME_URL).status_code, 200)

    def test_invalid_refresh_token_returns_401(self):
        response = self.client.post(REFRESH_URL, {"refresh": "not-a-token"})

        self.assertEqual(response.status_code, 401)

    def test_me_returns_only_public_fields(self):
        access = self.login().data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"id", "username", "email", "is_staff"})
        self.assertEqual(response.data["username"], "alice")
        self.assert_no_password(response)

    def test_me_without_token_returns_401(self):
        self.assertEqual(self.client.get(ME_URL).status_code, 401)

    def test_me_with_bad_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer garbage")

        self.assertEqual(self.client.get(ME_URL).status_code, 401)


# The only tests with throttling switched on. The rate is set here explicitly
# so the test doesn't depend on whatever settings.py says.
@override_settings(AUTH_THROTTLE_RATES={"login": "5/min", "register": "5/min"})
class ThrottleTests(AuthTestCase):
    def test_login_throttled_after_5_attempts(self):
        for _ in range(5):
            response = self.client.post(LOGIN_URL, {"username": "x", "password": "y"})
            self.assertEqual(response.status_code, 401)

        response = self.client.post(LOGIN_URL, {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 429)

    def test_register_throttled_after_5_attempts(self):
        for i in range(5):
            response = self.client.post(
                REGISTER_URL, register_payload(username=f"u{i}", email=f"u{i}@example.com")
            )
            self.assertEqual(response.status_code, 201)

        response = self.client.post(
            REGISTER_URL, register_payload(username="u5", email="u5@example.com")
        )
        self.assertEqual(response.status_code, 429)


def with_num_proxies(n):
    """override_settings for REST_FRAMEWORK["NUM_PROXIES"] (DRF reloads its settings on change)."""
    from django.conf import settings

    return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": n})


@override_settings(AUTH_THROTTLE_RATES={"login": "2/min", "register": "2/min"})
class ThrottleClientIpTests(AuthTestCase):
    """Throttling must count the REAL client, and a client must not be able to
    escape the limit by sending a made-up X-Forwarded-For header."""

    PROXY = "10.0.0.1"  # REMOTE_ADDR seen by Django behind PythonAnywhere's proxy

    def login_from(self, forwarded_for, remote_addr=PROXY):
        return self.client.post(
            LOGIN_URL, {"username": "x", "password": "y"},
            REMOTE_ADDR=remote_addr, HTTP_X_FORWARDED_FOR=forwarded_for,
        )

    def use_up_limit(self, forwarded_for, remote_addr=PROXY):
        for _ in range(2):
            self.assertEqual(self.login_from(forwarded_for, remote_addr).status_code, 401)

    @with_num_proxies(1)
    def test_behind_proxy_each_client_ip_has_its_own_limit(self):
        self.use_up_limit("203.0.113.5")
        self.assertEqual(self.login_from("203.0.113.5").status_code, 429)
        # Another visitor behind the same proxy is NOT blocked.
        self.assertEqual(self.login_from("198.51.100.7").status_code, 401)

    @with_num_proxies(1)
    def test_behind_proxy_a_faked_header_does_not_reset_the_limit(self):
        # The proxy APPENDS the real IP; anything before it came from the client.
        self.use_up_limit("203.0.113.5")
        response = self.login_from("1.2.3.4, 203.0.113.5")
        self.assertEqual(response.status_code, 429)

    @with_num_proxies(0)
    def test_without_proxy_the_header_is_ignored(self):
        # Local/direct: X-Forwarded-For is whatever the client typed, so only REMOTE_ADDR counts.
        self.use_up_limit("1.1.1.1", remote_addr="192.0.2.9")
        self.assertEqual(self.login_from("2.2.2.2", remote_addr="192.0.2.9").status_code, 429)
        self.assertEqual(self.login_from("1.1.1.1", remote_addr="192.0.2.10").status_code, 401)

    def test_default_setting_is_not_drfs_trust_everything(self):
        from django.conf import settings

        # DRF's default (None) would trust a client-supplied X-Forwarded-For.
        self.assertIsNotNone(settings.REST_FRAMEWORK["NUM_PROXIES"])
