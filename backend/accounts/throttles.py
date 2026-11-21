from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


class AuthRateThrottle(ScopedRateThrottle):
    """
    Limits requests per client IP for one "scope" (e.g. "login").

    Same as DRF's ScopedRateThrottle, except the rate is read from
    settings.AUTH_THROTTLE_RATES on every request. DRF's version copies its
    rates once at import time, which makes them impossible to change in tests.
    A rate of None means "no limit".
    """

    def get_rate(self):
        return settings.AUTH_THROTTLE_RATES.get(self.scope)
