from __future__ import annotations

import copy

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar, overload

from asgiref.local import Local


T = TypeVar("T")

_local = Local()
_MISSING = object()
_DEFAULT_SCOPE: str | None = None


def _scope_map() -> dict[str | None, list[dict[str, Any]]]:
    scopes = getattr(_local, "scopes", None)
    if scopes is None:
        scopes = {}
        _local.scopes = scopes
    return scopes


def _frames(scope: str | None) -> list[dict[str, Any]] | None:
    return _scope_map().get(scope)


def enabled(*, scope: str | None = None) -> bool:
    """Return whether a stash scope is active for this execution context."""
    return bool(_frames(scope))


def enable() -> None:
    """
    Open a fresh default stash scope for this execution context.

    Drops any previously open named or nested scopes. Prefer
    ``StashMiddleware``, ``StashCommandMixin``, or ``stash_scope()`` so
    lifetime is bounded.
    """
    _local.scopes = {_DEFAULT_SCOPE: [{}]}


def disable() -> None:
    """Close every stash scope and drop all stored values for this context."""
    _local.scopes = {}


def _store(value: Any) -> Any:
    return copy.copy(value)


def _retrieve(value: Any) -> Any:
    return copy.copy(value)


def _lookup(key: str, scope: str | None) -> Any:
    stack = _frames(scope)
    if not stack:
        return _MISSING
    for frame in reversed(stack):
        value = frame.get(key, _MISSING)
        if value is not _MISSING:
            return value
    return _MISSING


def get(key: str, default: Any = None, *, scope: str | None = None) -> Any:
    """Return a stashed value, or ``default`` on miss / when no scope is active."""
    value = _lookup(key, scope)
    if value is _MISSING:
        return default
    return _retrieve(value)


def set(key: str, value: Any, *, scope: str | None = None) -> None:
    """
    Store ``value`` under ``key`` in the innermost block of ``scope``.

    No-op when that scope is not active (avoids sticky process-level state).
    """
    stack = _frames(scope)
    if not stack:
        return
    stack[-1][key] = _store(value)


def clear(key: str | None = None, *, scope: str | None = None) -> None:
    """
    Clear one key, or the current innermost block when ``key`` is omitted.

    ``clear("k")`` removes ``k`` from every nested block of ``scope``, so a
    later ``get_or_set`` reloads even if an outer block had it. ``clear()``
    empties only the innermost block, leaving outer values of the same
    name intact.
    """
    stack = _frames(scope)
    if not stack:
        return
    if key is None:
        stack[-1].clear()
        return
    for frame in stack:
        frame.pop(key, None)


def get_or_set(key: str, loader: Callable[[], T], *, scope: str | None = None) -> T:
    """
    Return a stashed value, or call ``loader``, stash the result, and return it.

    Looks innermost-first through nested blocks of ``scope``. A miss stores
    on the current (innermost) block. When that scope is not active, always
    calls ``loader()`` and does not store.
    """
    stack = _frames(scope)
    if not stack:
        return loader()

    value = _lookup(key, scope)
    if value is not _MISSING:
        return _retrieve(value)

    loaded = loader()
    stack[-1][key] = _store(loaded)
    return _retrieve(loaded)


def _memo_key(
    func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    qualname = f"{func.__module__}.{func.__qualname__}"
    if not args and not kwargs:
        return qualname
    return f"{qualname}:{args!r}:{sorted(kwargs.items())!r}"


@overload
def memoize(func: Callable[..., T]) -> Callable[..., T]: ...


@overload
def memoize(
    *,
    key: str | None = None,
    scope: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]: ...


def memoize(
    func: Callable[..., T] | None = None,
    *,
    key: str | None = None,
    scope: str | None = None,
) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Memoize a function into the active stash scope.

    ``@memoize`` derives a key from the function and call arguments.
    ``@memoize(key="...")`` uses a fixed key (argument values ignored).
    ``@memoize(scope="...")`` stores in a named scope.
    Outside a scope, the function always runs normally.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            cache_key = key if key is not None else _memo_key(fn, args, kwargs)
            return get_or_set(cache_key, lambda: fn(*args, **kwargs), scope=scope)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


@contextmanager
def stash_scope(name: str | None = None) -> Iterator[None]:
    """
    Open a stash scope for a block of work.

    ``stash_scope()`` uses the default scope (the same one
    ``StashMiddleware`` and ``StashCommandMixin`` open). Nested calls with
    the same name stack: inner writes stay in the inner block, ``get``
    looks there first then outward, and exiting the inner block restores
    the outer values.

    ``stash_scope("wagtail")`` is a separate named scope that can be open at
    the same time as the default. ``get`` / ``set`` / ``get_or_set`` /
    ``clear`` take ``scope="wagtail"`` to read or write it. In a reusable
    package, pass a unique name (the package name) for values that should
    not collide with the project; omit the name when the rest of the
    project is meant to ``get`` them.

    Use this in your own middleware instead of ``StashMiddleware`` — the
    better option in a reusable package, so installers don't have to add
    third-party middleware — or around a unit of work in a Celery task,
    test, or loop. Do not wrap a Django view: ``TemplateResponse`` is
    rendered after the view returns, so a mixin or decorator would close
    too early. For a management command, prefer ``StashCommandMixin``.
    """
    scopes = _scope_map()
    stack = scopes.setdefault(name, [])
    stack.append({})
    try:
        yield
    finally:
        current = _scope_map().get(name)
        if current is stack and stack:
            stack.pop()
            if not stack:
                _scope_map().pop(name, None)
