from django.contrib import admin
from django.urls import include, path, re_path

from config.views import api_not_found, frontend_app

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("files.urls")),
    # Any other api/.../ URL -> JSON 404, never an HTML page. Only URLs ending in "/",
    # so "/api/files" still gets Django's redirect to "/api/files/" (APPEND_SLASH).
    re_path(r"^api/(?:.*/)?$", api_not_found),
    # Everything else is a React page -> index.html. Must stay LAST, and must not
    # match api/, admin/ or static/.
    re_path(r"^(?!(?:api|admin|static)(?:/|$)).*$", frontend_app),
]
