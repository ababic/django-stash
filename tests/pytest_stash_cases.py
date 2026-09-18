"""Pytest cases for stash.pytest_plugin.

Not named ``test_*.py``, so Django's runner does not collect this module.
``tests/test_testing.py`` runs it under pytest.
"""

from __future__ import annotations

import pytest

import stash


def test_unmarked_test_does_not_activate() -> None:
    stash.disable()
    assert not stash.enabled()
    stash.set("k", "nope")
    assert stash.get("k") is None


@pytest.mark.stash_scope
def test_marker_opens_default_scope() -> None:
    assert stash.enabled()
    stash.set("k", "marker")
    assert stash.get("k") == "marker"


@pytest.mark.stash_scope
def test_marker_does_not_keep_the_previous_test_value() -> None:
    assert stash.get("k") is None
    assert stash.enabled()


@pytest.mark.stash_scope("pkg")
def test_marker_opens_named_scope() -> None:
    assert stash.enabled()
    assert stash.enabled(scope="pkg")
    stash.set("k", "named", scope="pkg")
    assert stash.get("k", scope="pkg") == "named"
    assert stash.get("k") is None


def test_marker_is_off_again_for_an_unmarked_test() -> None:
    assert not stash.enabled()
    assert not stash.enabled(scope="pkg")
    stash.set("k", "nope")
    assert stash.get("k") is None


def test_fixture_opens_default_scope(stash_scope) -> None:
    assert stash.enabled()
    stash.set("k", "fixture")
    assert stash.get("k") == "fixture"


@pytest.mark.stash_scope("pkg")
def test_fixture_uses_marker_names(stash_scope) -> None:
    assert stash.enabled()
    assert stash.enabled(scope="pkg")
    stash.set("page", "home", scope="pkg")
    assert stash.get("page", scope="pkg") == "home"


@pytest.mark.stash_scope("pkg")
class TestClassMarker:
    def test_one(self) -> None:
        assert stash.enabled(scope="pkg")
        stash.set("k", "class")
        assert stash.get("k") == "class"

    def test_two_is_a_fresh_scope(self) -> None:
        assert stash.get("k") is None
        assert stash.enabled()
        assert stash.enabled(scope="pkg")
