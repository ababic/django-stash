from __future__ import annotations

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
    scope, closed when the command finishes (including on error). Useful in
    an app you own and in a reusable package — installers never see it.

    Nested ``stash_scope()`` calls stack on this scope, so a per-item
    ``with stash.stash_scope():`` keeps command-level values and drops
    item-level ones when the block ends. In a reusable package, use a
    unique name for values the host should not see.
    """

    def execute(self, *args: Any, **options: Any) -> Any:
        with stash_scope():
            return super().execute(*args, **options)
