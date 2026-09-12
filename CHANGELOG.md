# Changelog

## 0.2.0

- `StashMiddleware` is now sync- and async-capable, so it no longer forces Django to adapt the rest of an ASGI middleware chain.
- README rewrite: plain, self-contained examples; "Where this fits" / "Where this doesn't fit"; an alternatives comparison against `django-request-cache`, Django's cache framework, `functools.lru_cache`, and bare thread-locals.

## 0.1.0

- Initial release: scoped ambient memoization via `asgiref.local.Local`, `StashMiddleware`, and `stash_scope()`.
