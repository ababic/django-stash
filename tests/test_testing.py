from __future__ import annotations

import os
import subprocess
import sys
import unittest

from importlib.metadata import entry_points
from io import StringIO
from pathlib import Path

from django.test import SimpleTestCase

import stash

from stash.pytest_plugin import scope_names_from_marker
from stash.testing import StashTestMixin, activate


ROOT = Path(__file__).resolve().parents[1]


class _Marker:
    def __init__(self, args: tuple[object, ...] = (), kwargs: dict | None = None) -> None:
        self.args = args
        self.kwargs = kwargs or {}


class StashTestMixinTests(StashTestMixin, SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        stash.set("from_setup", 1)

    def tearDown(self) -> None:
        self.assertTrue(stash.enabled())
        self.assertEqual(stash.get("from_setup"), 1)
        super().tearDown()

    def test_scope_is_open_and_setup_value_is_visible(self) -> None:
        calls = {"n": 0}

        def loader() -> str:
            calls["n"] += 1
            return "v"

        self.assertEqual(stash.get("from_setup"), 1)
        self.assertEqual(stash.get_or_set("k", loader), "v")
        self.assertEqual(stash.get_or_set("k", loader), "v")
        self.assertEqual(calls["n"], 1)

    async def test_async_method_sees_the_scope_opened_in_setUp(self) -> None:
        self.assertTrue(stash.enabled())
        self.assertEqual(stash.get("from_setup"), 1)
        stash.set("k", "async")
        self.assertEqual(stash.get("k"), "async")


class NamedScopeMixinTests(StashTestMixin, SimpleTestCase):
    stash_scopes = ("pkg",)

    def test_named_scope_is_open_beside_the_default(self) -> None:
        self.assertTrue(stash.enabled())
        self.assertTrue(stash.enabled(scope="pkg"))
        stash.set("k", "named", scope="pkg")
        self.assertEqual(stash.get("k", scope="pkg"), "named")
        self.assertIsNone(stash.get("k"))


class StashTestMixinLifecycleTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        stash.disable()

    def tearDown(self) -> None:
        stash.disable()
        super().tearDown()

    def test_string_stash_scopes_and_cleanup(self) -> None:
        class Probe(StashTestMixin, unittest.TestCase):
            stash_scopes = "pkg"

            def test_x(self) -> None:
                pass

        case = Probe("test_x")
        case.setUp()
        try:
            self.assertTrue(stash.enabled())
            self.assertTrue(stash.enabled(scope="pkg"))
            stash.set("k", "v", scope="pkg")
            self.assertEqual(stash.get("k", scope="pkg"), "v")
        finally:
            case.doCleanups()
        self.assertFalse(stash.enabled())
        self.assertFalse(stash.enabled(scope="pkg"))
        self.assertIsNone(stash.get("k", scope="pkg"))

    def test_empty_scope_names_are_skipped(self) -> None:
        class Probe(StashTestMixin, unittest.TestCase):
            stash_scopes = ("", "pkg")

            def test_x(self) -> None:
                pass

        case = Probe("test_x")
        case.setUp()
        try:
            self.assertTrue(stash.enabled())
            self.assertTrue(stash.enabled(scope="pkg"))
            self.assertFalse(stash.enabled(scope=""))
        finally:
            case.doCleanups()

    def test_setup_failure_still_disables(self) -> None:
        class Boom(StashTestMixin, unittest.TestCase):
            def setUp(self) -> None:
                super().setUp()
                stash.set("k", "x")
                raise RuntimeError("boom")

            def test_x(self) -> None:
                pass

        result = unittest.TestResult()
        Boom("test_x").run(result)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(stash.enabled())
        self.assertIsNone(stash.get("k"))

    def test_enable_inside_a_mixin_test_does_not_leak(self) -> None:
        class Probe(StashTestMixin, unittest.TestCase):
            def test_a(self) -> None:
                stash.enable()
                stash.set("leak", 1)

            def test_b(self) -> None:
                self.assertTrue(stash.enabled())
                self.assertIsNone(stash.get("leak"))

        suite = unittest.TestSuite(
            (Probe("test_a"), Probe("test_b")),
        )
        result = unittest.TextTestRunner(stream=StringIO(), verbosity=0).run(suite)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertFalse(stash.enabled())


class ActivateTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        stash.disable()

    def tearDown(self) -> None:
        self.assertFalse(stash.enabled())
        self.assertFalse(stash.enabled(scope="pkg"))
        super().tearDown()

    @activate()
    def test_decorator_opens_the_default_scope(self) -> None:
        self.assertTrue(stash.enabled())
        stash.set("k", 1)
        self.assertEqual(stash.get("k"), 1)

    @activate("pkg")
    def test_decorator_opens_a_named_scope(self) -> None:
        self.assertTrue(stash.enabled())
        self.assertTrue(stash.enabled(scope="pkg"))
        stash.set("k", "v", scope="pkg")
        self.assertEqual(stash.get("k", scope="pkg"), "v")
        self.assertIsNone(stash.get("k"))

    @activate("pkg", "other")
    def test_decorator_opens_each_named_scope(self) -> None:
        self.assertTrue(stash.enabled(scope="pkg"))
        self.assertTrue(stash.enabled(scope="other"))

    @activate()
    async def test_async_decorator_opens_the_scope_inside_the_coroutine(self) -> None:
        self.assertTrue(stash.enabled())
        stash.set("k", "async")
        self.assertEqual(stash.get("k"), "async")

    def test_bare_decorator_is_rejected(self) -> None:
        with self.assertRaises(TypeError):

            @activate
            def _inner() -> None:
                pass

    def test_non_string_scope_name_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            activate(1)

    def test_context_manager_starts_fresh_and_disables_on_exit(self) -> None:
        stash.enable()
        stash.set("leak", 1)
        with activate():
            self.assertIsNone(stash.get("leak"))
            self.assertTrue(stash.enabled())
            stash.set("k", 2)
            self.assertEqual(stash.get("k"), 2)
        self.assertIsNone(stash.get("leak"))
        self.assertIsNone(stash.get("k"))

        with activate("pkg"):
            self.assertTrue(stash.enabled())
            self.assertTrue(stash.enabled(scope="pkg"))
            stash.enable()
            stash.set("k", "replaced")
        self.assertIsNone(stash.get("k"))

    def test_enter_drops_an_outer_scope_and_does_not_restore_it(self) -> None:
        with stash.stash_scope():
            stash.set("outer", 1)
            with activate():
                self.assertIsNone(stash.get("outer"))
                self.assertTrue(stash.enabled())
                stash.set("inner", 2)
            self.assertFalse(stash.enabled())
            self.assertIsNone(stash.get("outer"))
            self.assertIsNone(stash.get("inner"))


class PytestPluginTests(SimpleTestCase):
    def test_scope_names_from_marker(self) -> None:
        self.assertIsNone(scope_names_from_marker(None))
        self.assertEqual(scope_names_from_marker(_Marker(())), ())
        self.assertEqual(scope_names_from_marker(_Marker(("pkg", ""))), ("pkg", ""))
        with self.assertRaises(TypeError):
            scope_names_from_marker(_Marker((), {"scope": "pkg"}))

    def test_pytest_plugin_entry_point_is_registered(self) -> None:
        found = {
            ep.name: ep.value
            for ep in entry_points(group="pytest11")
            if ep.name == "django_stash"
        }
        self.assertEqual(found, {"django_stash": "stash.pytest_plugin"})

    def test_pytest_marker_and_fixture(self) -> None:
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env.pop("DJANGO_SETTINGS_MODULE", None)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "stash.pytest_plugin",
                "-p",
                "no:cacheprovider",
                str(ROOT / "tests" / "pytest_stash_cases.py"),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + "\n" + completed.stderr,
        )
