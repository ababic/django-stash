# Changelog

## Unreleased

- Named scopes (`stash_scope("wagtail")` + `scope=` on get/set/get_or_set/clear/memoize) can be open alongside the default scope. Nested `stash_scope()` calls with the same name stack instead of replacing. Packages use a unique name for private values; the default scope when the host should read them. `StashCommandMixin.stash_scopes` opens extra named scopes for a command run.

## 0.3.0

- Add `StashCommandMixin` to open a stash scope around each management command run.
- README: install section splits app vs package setup — `StashMiddleware` for an app you own, `stash_scope()` in middleware you control so package installers don't have to add a third-party class.

## 0.2.1

- README: alternatives comparison table (`django-request-cache`, Django's cache framework, `functools.lru_cache`, bare thread-locals) and a genuinely request-derived hero example (hostname-based tenant resolution) in place of one that never touched `request`.

## 0.2.0

- `StashMiddleware` is now sync- and async-capable, so it no longer forces Django to adapt the rest of an ASGI middleware chain.
- README rewrite: plain, self-contained examples; "Where this fits" / "Where this doesn't fit"; an alternatives comparison against `django-request-cache`, Django's cache framework, `functools.lru_cache`, and bare thread-locals.

## 0.1.0

- Initial release: scoped ambient memoization via `asgiref.local.Local`, `StashMiddleware`, and `stash_scope()`.
