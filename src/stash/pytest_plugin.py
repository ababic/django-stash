"""pytest fixture and ``stash_scope`` marker for tests that call stash directly.

Registered through the ``pytest11`` entry point when django-stash is
installed. Nothing is activated unless a test requests the ``stash_scope``
fixture or is marked ``pytest.mark.stash_scope``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from stash.testing import activate


def scope_names_from_marker(marker: object | None) -> tuple[str, ...] | None:
    """Return named scopes from a ``stash_scope`` mark, or None if unmarked."""
    if marker is None:
        return None
    kwargs = getattr(marker, "kwargs", None) or {}
    if kwargs:
        raise TypeError(
            "pytest.mark.stash_scope takes scope names as positional arguments, "
            'for example @pytest.mark.stash_scope("wagtail").'
        )
    return tuple(getattr(marker, "args", ()))


@pytest.fixture
def stash_scope(request: pytest.FixtureRequest) -> Iterator[None]:
    """Open a fresh default stash scope for this test and disable it afterwards.

    A ``pytest.mark.stash_scope`` marker on the test, its class, or its
    module also opens those named scopes. The default scope is always opened.
    """
    names = scope_names_from_marker(request.node.get_closest_marker("stash_scope"))
    with activate(*(names or ())):
        yield


@pytest.fixture(autouse=True)
def _stash_scope_marker(request: pytest.FixtureRequest) -> Iterator[None]:
    names = scope_names_from_marker(request.node.get_closest_marker("stash_scope"))
    if names is None or "stash_scope" in request.fixturenames:
        yield
        return
    with activate(*names):
        yield


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "stash_scope(*names): open a fresh default stash scope for the test, "
        "plus any named scopes, and disable every scope when the test ends.",
    )
