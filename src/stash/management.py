from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from typing import Any

from stash.api import stash_scope


class StashCommandMixin:
    """
    Open a stash scope for the duration of one management command run.

    Mix this in ahead of ``BaseCommand`` (or ``AppCommand`` / ``LabelCommand``):

        class Command(StashCommandMixin, BaseCommand):
            def handle(self, *args, **options):
                ...

    Analogous to ``StashMiddleware`` for HTTP: each invocation gets a fresh
    default scope, closed when the command finishes (including on error).
    Useful in an app you own and in a reusable package — installers never
    see it.

    Set ``stash_scopes`` to also open named scopes for the run — a package
    that stashes under ``scope="wagtail"`` should set
    ``stash_scopes = ("wagtail",)`` (a single string is also accepted). The
    default scope stays open either way.

    Nested ``stash_scope()`` calls stack on the default scope, so a per-item
    ``with stash.stash_scope():`` keeps command-level values and drops
    item-level ones when the block ends.
    """

    stash_scopes: str | Sequence[str] = ()

    def execute(self, *args: Any, **options: Any) -> Any:
        names = self.stash_scopes
        extra = (names,) if isinstance(names, str) else tuple(names)
        extra = tuple(name for name in extra if name)
        with ExitStack() as stack:
            stack.enter_context(stash_scope())
            for name in extra:
                stack.enter_context(stash_scope(name))
            return super().execute(*args, **options)
