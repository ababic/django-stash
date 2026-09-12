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

    Don't wrap the same run in ``stash_scope()`` as well. Nested scopes
    replace rather than stack, and exiting the inner block would close the
    command's scope. For a fresh memo per item, skip the mixin and use
    ``stash_scope()`` in the loop instead.
    """

    def execute(self, *args: Any, **options: Any) -> Any:
        with stash_scope():
            return super().execute(*args, **options)
