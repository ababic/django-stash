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
