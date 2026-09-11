from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from stash.api import disable, enable


class StashMiddleware:
    """
    Open a stash scope for the duration of one HTTP request.

    Outside this middleware (management commands, Celery tasks, etc.) stash
    reads miss and writes no-op, so values cannot leak across units of work on
    a reused worker thread.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        enable()
        try:
            return self.get_response(request)
        finally:
            disable()
