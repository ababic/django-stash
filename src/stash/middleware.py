from __future__ import annotations

from collections.abc import Awaitable, Callable

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse

from stash.api import disable, enable


class StashMiddleware:
    """
    Open a stash scope for the duration of one HTTP request.

    Works as sync or async middleware, so it does not force Django to adapt the
    middleware chain when running under ASGI.

    For a website or web app you own, this is the easy way to get started. In
    a reusable package, prefer wrapping ``get_response`` in
    ``stash.stash_scope()`` from middleware you already require (or one of
    your own), so installers don't have to add this class. Put
    ``StashMiddleware`` first if both are in use: it opens the default scope,
    and a later ``stash_scope()`` stacks on it (or ``stash_scope("name")``
    runs alongside it). For values the project should not see, use a unique
    name (the package name) and pass ``scope=`` at every call site.

    Outside a scope (management commands, Celery tasks, etc.) stash reads miss
    and writes no-op, so values cannot leak across units of work on a reused
    worker thread.
    """

    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse | Awaitable[HttpResponse]],
    ) -> None:
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> HttpResponse | Awaitable[HttpResponse]:
        if iscoroutinefunction(self):
            return self.__acall__(request)
        enable()
        try:
            return self.get_response(request)  # type: ignore[return-value]
        finally:
            disable()

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        enable()
        try:
            return await self.get_response(request)  # type: ignore[misc]
        finally:
            disable()
