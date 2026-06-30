from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("user_id"):
            messages.warning(request, "You must be logged in to access this page.")
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return wrapper
