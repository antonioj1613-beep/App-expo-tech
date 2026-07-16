from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from .user_helpers import STALE_SESSION_MESSAGE, get_logged_in_user, invalidate_stale_session


def login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("user_id"):
            if _wants_json(request):
                return JsonResponse({"error": "Not authenticated."}, status=401)
            messages.warning(request, "You must be logged in to access this page.")
            return redirect("login")

        user = get_logged_in_user(request)
        if not user:
            invalidate_stale_session(request)
            if _wants_json(request):
                return JsonResponse({"error": STALE_SESSION_MESSAGE}, status=401)
            messages.warning(request, STALE_SESSION_MESSAGE)
            return redirect("login")

        request.lisa_user = user
        return view_func(request, *args, **kwargs)

    return wrapper


def _wants_json(request):
    accept = request.headers.get("Accept", "")
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in accept
        or request.path.endswith("/submit/")
        or "/api/" in request.path
    )
