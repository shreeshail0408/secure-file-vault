from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe


@require_safe  # GET/HEAD only: a stray POST to /something gets 405, not the page
def frontend_app(request):
    """Serve the React app's index.html for every non-API URL (/, /login, /register, ...).

    React Router decides what to show from the URL in the browser, so a reload on
    /register must also return index.html. The JS/CSS it loads come from /static/.
    """
    index = settings.FRONTEND_DIST / "index.html"
    try:
        html = index.read_text(encoding="utf-8")
    except FileNotFoundError:
        return HttpResponse(
            "The frontend is not built yet. Run `npm run build` in frontend/.",
            status=503, content_type="text/plain",
        )
    response = HttpResponse(html)
    # Always revalidate, so a new build shows up right after a reload.
    response["Cache-Control"] = "no-cache"
    return response


@csrf_exempt  # it only ever answers 404; without this a POST would get an HTML CSRF page
def api_not_found(request):
    """Unknown /api/... URL: a JSON 404 like the rest of the API (the frontend expects
    {"detail": ...}). A route, not a handler404, so it is JSON with DEBUG=True too."""
    return JsonResponse({"detail": "Not found."}, status=404)
