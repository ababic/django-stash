from __future__ import annotations

from io import StringIO

from asgiref.sync import iscoroutinefunction
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings

import stash

from stash.middleware import StashMiddleware


class StashApiTests(SimpleTestCase):
    def setUp(self) -> None:
        stash.disable()

    def tearDown(self) -> None:
        stash.disable()

    def test_inactive_get_or_set_does_not_store(self) -> None:
        calls = {"n": 0}

        def loader():
            calls["n"] += 1
            return ["value"]

        self.assertEqual(stash.get_or_set("k", loader), ["value"])
        self.assertEqual(stash.get_or_set("k", loader), ["value"])
        self.assertEqual(calls["n"], 2)
        self.assertIsNone(stash.get("k"))

    def test_active_get_or_set_memoizes(self) -> None:
        calls = {"n": 0}

        def loader():
            calls["n"] += 1
            return ["value"]

        with stash.stash_scope():
            self.assertEqual(stash.get_or_set("k", loader), ["value"])
            self.assertEqual(stash.get_or_set("k", loader), ["value"])
            self.assertEqual(calls["n"], 1)

    def test_mutation_of_returned_value_does_not_poison_stash(self) -> None:
        with stash.stash_scope():
            value = stash.get_or_set("k", lambda: ["a", "b"])
            value.append("c")
            self.assertEqual(stash.get("k"), ["a", "b"])

    def test_clear_key_and_all(self) -> None:
        with stash.stash_scope():
            stash.set("a", 1)
            stash.set("b", 2)
            stash.clear("a")
            self.assertIsNone(stash.get("a"))
            self.assertEqual(stash.get("b"), 2)
            stash.clear()
            self.assertIsNone(stash.get("b"))

    def test_set_is_noop_outside_scope(self) -> None:
        stash.set("k", "nope")
        self.assertIsNone(stash.get("k"))

    def test_memoize_fixed_key(self) -> None:
        calls = {"n": 0}

        @stash.memoize(key="fixed")
        def compute(x: int) -> int:
            calls["n"] += 1
            return x * 2

        with stash.stash_scope():
            self.assertEqual(compute(2), 4)
            self.assertEqual(compute(99), 4)  # fixed key ignores args
            self.assertEqual(calls["n"], 1)

    def test_memoize_derives_key_from_args(self) -> None:
        calls = {"n": 0}

        @stash.memoize
        def compute(x: int) -> int:
            calls["n"] += 1
            return x * 2

        with stash.stash_scope():
            self.assertEqual(compute(2), 4)
            self.assertEqual(compute(2), 4)
            self.assertEqual(compute(3), 6)
            self.assertEqual(calls["n"], 2)

    def test_scope_clears_on_exit(self) -> None:
        with stash.stash_scope():
            stash.set("k", "v")
            self.assertTrue(stash.enabled())
        self.assertFalse(stash.enabled())
        self.assertIsNone(stash.get("k"))

    async def test_scope_in_async_code(self) -> None:
        calls = {"n": 0}

        def loader():
            calls["n"] += 1
            return "v"

        with stash.stash_scope():
            self.assertEqual(stash.get_or_set("k", loader), "v")
            self.assertEqual(stash.get_or_set("k", loader), "v")
            self.assertEqual(calls["n"], 1)
        self.assertFalse(stash.enabled())


class StashMiddlewareTests(SimpleTestCase):
    def test_middleware_memoizes_within_request(self) -> None:
        response = self.client.get("/probe/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "calls=1;same=True")
        self.assertFalse(stash.enabled())

    @override_settings(MIDDLEWARE=["django.middleware.common.CommonMiddleware"])
    def test_without_middleware_loader_runs_twice(self) -> None:
        response = self.client.get("/probe/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "calls=2;same=True")

    async def test_async_view_under_asgi(self) -> None:
        response = await self.async_client.get("/async-probe/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "calls=1;same=True")
        self.assertFalse(stash.enabled())

    async def test_sync_view_under_asgi(self) -> None:
        response = await self.async_client.get("/probe/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "calls=1;same=True")
        self.assertFalse(stash.enabled())

    def test_middleware_adapts_to_sync_and_async_chains(self) -> None:
        def sync_get_response(request):
            return HttpResponse()

        async def async_get_response(request):
            return HttpResponse()

        self.assertFalse(iscoroutinefunction(StashMiddleware(sync_get_response)))
        self.assertTrue(iscoroutinefunction(StashMiddleware(async_get_response)))


class StashCommandMixinTests(SimpleTestCase):
    def setUp(self) -> None:
        stash.disable()

    def tearDown(self) -> None:
        stash.disable()

    def test_mixin_memoizes_within_one_run(self) -> None:
        class ProbeCommand(stash.StashCommandMixin, BaseCommand):
            def handle(self, *args, **options):
                calls = {"n": 0}

                def loader():
                    calls["n"] += 1
                    return "v"

                stash.get_or_set("k", loader)
                stash.get_or_set("k", loader)
                self.stdout.write(str(calls["n"]))

        out = StringIO()
        call_command(ProbeCommand(), stdout=out)
        self.assertEqual(out.getvalue().strip(), "1")
        self.assertFalse(stash.enabled())
        self.assertIsNone(stash.get("k"))

    def test_without_mixin_loader_runs_twice(self) -> None:
        class BareCommand(BaseCommand):
            def handle(self, *args, **options):
                calls = {"n": 0}

                def loader():
                    calls["n"] += 1
                    return "v"

                stash.get_or_set("k", loader)
                stash.get_or_set("k", loader)
                self.stdout.write(str(calls["n"]))

        out = StringIO()
        call_command(BareCommand(), stdout=out)
        self.assertEqual(out.getvalue().strip(), "2")

    def test_scope_closes_when_handle_raises(self) -> None:
        class BoomCommand(stash.StashCommandMixin, BaseCommand):
            def handle(self, *args, **options):
                stash.set("k", 1)
                raise RuntimeError("nope")

        with self.assertRaises(RuntimeError):
            call_command(BoomCommand(), stdout=StringIO())
        self.assertFalse(stash.enabled())
        self.assertIsNone(stash.get("k"))

    def test_nested_scope_keeps_command_values(self) -> None:
        test = self

        class NestedCommand(stash.StashCommandMixin, BaseCommand):
            def handle(self, *args, **options):
                stash.set("tenant", "acme")
                items = []
                for i in (1, 2):
                    with stash.stash_scope():
                        test.assertEqual(stash.get("tenant"), "acme")
                        stash.set("item", i)
                        items.append(stash.get("item"))
                test.assertEqual(items, [1, 2])
                test.assertEqual(stash.get("tenant"), "acme")
                test.assertIsNone(stash.get("item"))
                self.stdout.write("ok")

        out = StringIO()
        call_command(NestedCommand(), stdout=out)
        self.assertEqual(out.getvalue().strip(), "ok")
        self.assertFalse(stash.enabled())


class StashNamedScopeTests(SimpleTestCase):
    def setUp(self) -> None:
        stash.disable()

    def tearDown(self) -> None:
        stash.disable()

    def test_named_and_default_scopes_are_independent(self) -> None:
        with stash.stash_scope():
            stash.set("k", "default")
            with stash.stash_scope("other"):
                stash.set("k", "named", scope="other")
                self.assertEqual(stash.get("k"), "default")
                self.assertEqual(stash.get("k", scope="other"), "named")
                self.assertTrue(stash.enabled())
                self.assertTrue(stash.enabled(scope="other"))
            self.assertIsNone(stash.get("k", scope="other"))
            self.assertFalse(stash.enabled(scope="other"))
            self.assertEqual(stash.get("k"), "default")

    def test_nested_same_name_stacks(self) -> None:
        with stash.stash_scope():
            stash.set("k", "outer")
            with stash.stash_scope():
                self.assertEqual(stash.get("k"), "outer")
                stash.set("k", "inner")
                self.assertEqual(stash.get("k"), "inner")
                stash.set("only_inner", 1)
            self.assertEqual(stash.get("k"), "outer")
            self.assertIsNone(stash.get("only_inner"))

    def test_get_or_set_stores_on_inner_frame(self) -> None:
        calls = {"n": 0}

        def loader():
            calls["n"] += 1
            return ["v"]

        with stash.stash_scope():
            stash.set("shared", "outer")
            with stash.stash_scope():
                self.assertEqual(stash.get_or_set("shared", loader), "outer")
                self.assertEqual(stash.get_or_set("inner", loader), ["v"])
                self.assertEqual(calls["n"], 1)
            self.assertEqual(stash.get("shared"), "outer")
            self.assertIsNone(stash.get("inner"))

    def test_clear_key_punches_through_outer_frames(self) -> None:
        with stash.stash_scope():
            stash.set("k", "outer")
            with stash.stash_scope():
                stash.set("k", "inner")
                stash.clear("k")
                self.assertIsNone(stash.get("k"))
            self.assertIsNone(stash.get("k"))

    def test_clear_without_key_empties_inner_frame_only(self) -> None:
        with stash.stash_scope():
            stash.set("outer", 1)
            with stash.stash_scope():
                stash.set("inner", 2)
                stash.clear()
                self.assertIsNone(stash.get("inner"))
                self.assertEqual(stash.get("outer"), 1)

    def test_named_get_or_set_and_memoize(self) -> None:
        calls = {"n": 0}

        @stash.memoize(scope="pkg")
        def compute() -> str:
            calls["n"] += 1
            return "v"

        with stash.stash_scope():
            with stash.stash_scope("pkg"):
                self.assertEqual(compute(), "v")
                self.assertEqual(compute(), "v")
                self.assertEqual(calls["n"], 1)
                self.assertEqual(stash.get_or_set("k", lambda: "x", scope="pkg"), "x")
            self.assertIsNone(stash.get("k", scope="pkg"))
            self.assertEqual(calls["n"], 1)
            self.assertEqual(compute(), "v")
            self.assertEqual(calls["n"], 2)

    def test_enable_drops_named_scopes(self) -> None:
        with stash.stash_scope("pkg"):
            stash.set("k", 1, scope="pkg")
            stash.enable()
            self.assertIsNone(stash.get("k", scope="pkg"))
            self.assertTrue(stash.enabled())
            self.assertFalse(stash.enabled(scope="pkg"))
