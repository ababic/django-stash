"""Opt-in scope fences for tests that call stash-using code directly."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import ExitStack
from functools import wraps
from typing import Any, TypeVar

from asgiref.sync import iscoroutinefunction

from stash.api import disable, stash_scope


T = TypeVar("T")


class activate:
    """
    Open a fresh stash scope for a test, then drop every scope on the way out.

    Opens the default scope, plus each name in ``names`` (``"wagtail"`` for
    a package that passes ``scope="wagtail"``). Entering calls ``disable()``
    first, so a scope a previous test left open is not visible here. Exiting
    calls ``disable()`` again, so ``enable()`` or a ``stash_scope()`` the
    test did not close cannot leak into the next test.

    Use it as a context manager or on a test function (sync or async).
    Parentheses are required::

        @activate()
        def test_tenant(self):
            stash.set("tenant", "acme")

        @activate("wagtail")
        def test_page(self):
            stash.set("page", "home", scope="wagtail")

    For a whole ``TestCase``, prefer ``StashTestMixin`` — subclasses can
    override ``stash_scopes``. ``@stash.stash_scope()`` is the other tool:
    it stacks on whatever is already open and restores it on exit. This one
    does not nest. Entering it clears an outer scope, and exiting does not
    put that scope back. Don't wrap a smaller block in ``activate()`` if
    the rest of the test still needs values from outside.

    Not the request opener. ``StashMiddleware`` calls ``enable()`` /
    ``disable()`` around the request and will throw this scope away if you
    drive the test client from inside it.
    """

    def __init__(self, *names: str) -> None:
        cleaned: list[str] = []
        for name in names:
            if not isinstance(name, str):
                if callable(name):
                    raise TypeError(
                        "stash scope names must be strings. "
                        "Decorate a test with @activate(), including the parentheses."
                    )
                raise TypeError(
                    f"stash scope names must be strings, not {type(name).__name__}"
                )
            if name:
                cleaned.append(name)
        self.names = tuple(cleaned)

    def __enter__(self) -> None:
        # Drop a leaked scope before opening ours. ``enable()`` in an earlier
        # test would otherwise sit underneath this frame and still be visible.
        disable()
        stack = ExitStack()
        try:
            stack.enter_context(stash_scope())
            for name in self.names:
                stack.enter_context(stash_scope(name))
        except Exception:
            stack.close()
            disable()
            raise
        self._stack = stack

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            self._stack.close()
        finally:
            disable()

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        if iscoroutinefunction(func):

            @wraps(func)
            async def awrapper(*args: Any, **kwargs: Any) -> T:
                with activate(*self.names):
                    return await func(*args, **kwargs)

            return awrapper

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with activate(*self.names):
                return func(*args, **kwargs)

        return wrapper


class StashTestMixin:
    """
    Open a fresh stash scope for each test method, and close it afterwards.

    Mix this in ahead of ``TestCase`` (or ``SimpleTestCase``)::

        class TenantTests(StashTestMixin, TestCase):
            def test_reads_tenant(self):
                stash.set("tenant", "acme")
                self.assertEqual(get_current_tenant(), "acme")

    The default scope is always opened, same as ``StashCommandMixin``.
    Set ``stash_scopes`` to also open named scopes — a package that stashes
    under ``scope="wagtail"`` should set ``stash_scopes = ("wagtail",)``
    (a single string is also accepted).

    ``setUp`` must chain to ``super()`` before any ``stash.set``. The scope
    is opened in this mixin's ``setUp``, and it is still open in
    ``tearDown``. Cleanup calls ``stash.disable()``, including when
    ``setUp`` raises after the scope was opened, so a test that calls
    ``enable()`` cannot leak into the next one.

    This is for tests that call stash-using code directly. Request tests
    should use ``StashMiddleware`` and the test client instead.
    ``StashMiddleware`` replaces whatever scope is active for the request
    and does not restore it.
    """

    stash_scopes: str | Sequence[str] = ()

    def setUp(self) -> None:
        super().setUp()
        names = self.stash_scopes
        extra = (names,) if isinstance(names, str) else tuple(names)
        opened = activate(*extra)
        opened.__enter__()
        self.addCleanup(opened.__exit__, None, None, None)
