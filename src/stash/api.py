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


def enabled() -> bool:
    """Return whether a stash scope is active for this execution context."""
    return bool(getattr(_local, "enabled", False))


def enable() -> None:
    """
    Open a stash scope for this execution context.

    Prefer ``StashMiddleware``, ``StashCommandMixin``, or ``stash_scope()``
    so lifetime is bounded.
    """
    _local.enabled = True
    _local.values = {}


def disable() -> None:
    """Close the stash scope and drop all stored values for this context."""
    _local.values = {}
    _local.enabled = False


def _values() -> dict[str, Any]:
    values = getattr(_local, "values", None)
    if values is None:
        values = {}
        _local.values = values
    return values


def _store(value: Any) -> Any:
    return copy.copy(value)


def _retrieve(value: Any) -> Any:
    return copy.copy(value)


def get(key: str, default: Any = None) -> Any:
    """Return a stashed value, or ``default`` on miss / when no scope is active."""
    if not enabled():
        return default
    value = _values().get(key, _MISSING)
    if value is _MISSING:
        return default
    return _retrieve(value)


def set(key: str, value: Any) -> None:
    """
    Store ``value`` under ``key`` when a scope is active.

    No-op when no scope is active (avoids sticky process-level state).
    """
    if not enabled():
        return
    _values()[key] = _store(value)


def clear(key: str | None = None) -> None:
    """Clear one key, or the entire stash when ``key`` is omitted."""
    if not enabled():
        return
    if key is None:
        _local.values = {}
        return
    _values().pop(key, None)


def get_or_set(key: str, loader: Callable[[], T]) -> T:
    """
    Return a stashed value, or call ``loader``, stash the result, and return it.

    When no scope is active, always calls ``loader()`` and does not store.
    """
    if not enabled():
        return loader()

    values = _values()
    value = values.get(key, _MISSING)
    if value is not _MISSING:
        return _retrieve(value)

    loaded = loader()
    values[key] = _store(loaded)
    return _retrieve(loaded)


def _memo_key(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
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
) -> Callable[[Callable[..., T]], Callable[..., T]]: ...


def memoize(
    func: Callable[..., T] | None = None,
    *,
    key: str | None = None,
) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Memoize a function into the active stash scope.

    ``@memoize`` derives a key from the function and call arguments.
    ``@memoize(key="...")`` uses a fixed key (argument values ignored).
    Outside a scope, the function always runs normally.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            cache_key = key if key is not None else _memo_key(fn, args, kwargs)
            return get_or_set(cache_key, lambda: fn(*args, **kwargs))

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


@contextmanager
def stash_scope() -> Iterator[None]:
    """
    Open a stash scope for a block of work.

    Use this in your own middleware instead of ``StashMiddleware`` — the
    better option in a reusable package, so installers don't have to add
    third-party middleware — or around a unit of work in a Celery task,
    test, or loop. For a management command, prefer ``StashCommandMixin``.
    Nested calls replace the previous scope rather than stacking.
    """
    enable()
    try:
        yield
    finally:
        disable()
