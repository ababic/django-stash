# django-stash

[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Remember a value for the rest of the current request, and read it back from anywhere — without passing `request` around.

```python
import stash

# middleware.py — the one place that actually has `request`
class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        stash.set("tenant", Tenant.objects.get(domain=request.get_host()))
        return self.get_response(request)


# models.py, templatetags/, signals.py — no `request` in sight
def get_current_tenant():
    return stash.get("tenant")
```

`TenantMiddleware` resolves the tenant from the hostname once, because that's the only place `request` is available. Every other call to `get_current_tenant()` during that request — from a model manager, a template tag, a signal handler — reads the same value back. Next request: middleware resolves it again. A scope has to be open for `stash.set` to stick — `StashMiddleware`, or `stash_scope()` in this same class. See [Install](#install).

This is **not** a cache backend. Nothing is shared between requests, processes, or workers. Values live only while a request is being handled, and are thrown away when it finishes.

## Install

```bash
pip install django-stash
```

Nothing is stored unless a scope is open. No `INSTALLED_APPS` entry needed.

If you want to use django-stash in an app you own — a website or web app — `StashMiddleware` makes it easy to get started:

```python
MIDDLEWARE = [
    "stash.middleware.StashMiddleware",
    # ...
]
```

If you want to use it in a package (an add-on, a performance monitoring tool, or a CMS framework), open the scope from middleware you already require, or add one of your own. That way installers don't have to add an unfamiliar third-party middleware to their project settings:

```python
import stash

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with stash.stash_scope():
            stash.set("tenant", Tenant.objects.get(domain=request.get_host()))
            return self.get_response(request)
```

The same `with` works in async middleware.

Management commands sit outside the request cycle, so `StashMiddleware` never runs. Mix `StashCommandMixin` onto the command so each invocation gets a stash scope — in an app you own, or in a package (installers never see it):

```python
from django.core.management.base import BaseCommand

import stash

class Command(stash.StashCommandMixin, BaseCommand):
    def handle(self, *args, **options):
        tenant = stash.get_or_set("tenant", load_tenant)
        self.stdout.write(str(tenant))
```

These openers compose. A package `stash_scope()` around `get_response` is safe even if the project also uses `StashMiddleware` — keep `StashMiddleware` first so it opens the request, then later middleware stacks on it. Use a [named scope](#named-scopes) when two packages would otherwise share a key like `"tenant"`.

## The problem it solves

Not every case needs `request` at all. Sometimes you just have something expensive, needed in several unrelated places during one request — a template tag, a model method, a serializer, a signal handler:

```python
# views.py
settings = SiteSettings.objects.get()

# templatetags/theme.py
settings = SiteSettings.objects.get()   # same query again

# models.py
settings = SiteSettings.objects.get()   # and again
```

The usual fixes are awkward: thread `request` through every function, hang attributes off `request`, or reach for a global cache and then worry about invalidation.

With stash, each call site asks for the value by name and the first one pays:

```python
import stash

def get_site_settings():
    return stash.get_or_set("site_settings", lambda: SiteSettings.objects.get())
```

## Where this fits

Reach for stash when a value is expensive, needed in more than one place during a single request, and awkward to get to from where you are:

- **A request-derived value needed somewhere without `request`.** This is the example at the top: something that can only be resolved from the hostname, a header, or a cookie — the current tenant, the authenticated API client, an A/B test bucket — computed once where `request` exists, then read back from wherever it doesn't.
- **A check that fans out across a page.** A changelist renders 50 rows and calls `can_edit(obj)` for each. If `can_edit` starts with something request-wide — "is this user a reviewer this month" — that shouldn't be recomputed 50 times.
- **You're about to write `request._cached_thing = ...`.** This pattern already exists in most Django codebases: stash something on `request` in middleware, read it back everywhere else. It works, but it only works where `request` is reachable, and it leaks the caching detail into every call site. `stash.get_or_set` is the same idea, usable from anywhere, without a `request` reference.
- **A value that must be refreshed mid-request after a write.** Read settings early; a view updates them; later code in the *same* request must see the new value. One `stash.clear("site_settings")` call after the write handles it — see [`clear`](#get-set-clear) below.
- **Batch scripts, one memo per unit of work.** Mix `StashCommandMixin` onto a management command to scope the whole run, and wrap each row in `stash_scope()` so per-item memos die with the block. See [Nested scopes](#nested-scopes).

## Where this doesn't fit

- **You want the answer shared across requests, workers, or deploys.** That's Django's cache framework (`django.core.cache`, backed by Redis/Memcached/the DB). Stash never outlives one scope — put it in front of that cache as L1 if you want both.
- **The value needs to reach other processes.** Stash is per-process, per-scope. One worker's stash tells another worker nothing.
- **A pure function with no invalidation need, no request in the picture.** `functools.lru_cache` is simpler and doesn't need a scope at all.

## Alternatives

| | Scope | Needs `request`? | Cost per hit | Crosses requests / processes? | Invalidation |
|---|---|---|---|---|---|
| **stash** | One request, a management command run, or a `stash_scope()` block | No | Dict lookup | Never | Automatic when the scope ends; `clear()` any time before that |
| **[`django-request-cache`](https://github.com/anexia/django-request-cache)** | One request | Yes — exposes the *whole* request globally to get one | Attribute lookup | No | Automatic at request end only |
| **`request._cached_x`** (manual) | One request | Yes, at every call site | Attribute lookup | No | Manual, ad hoc |
| **Django's cache framework** | Until TTL, eviction, or delete | No | locmem: lock + dict. Redis/Memcached/DB: network round trip + (de)serialization, every call | Yes — that's the point | TTL, `cache.delete()`, or signals |
| **`functools.lru_cache`** | Process lifetime | No | Dict lookup | Accidentally, forever — same answer until the process restarts | None, short of calling `cache_clear()` yourself |
| **Bare thread-local / module global** | However long you remember to keep it valid | No | Dict/attribute lookup | Accidentally — sync workers reuse a thread across requests | Whatever you remember to write, wherever you remember to write it |

The last row is the trap: a hand-rolled `threading.local()` or `asgiref.Local()` looks identical to stash until a worker process reuses its thread for a second request and the old value is still sitting there. Stash's storage is the same mechanism (`asgiref.local.Local`), but the lifetime is never left to memory — `StashMiddleware`, `StashCommandMixin`, or `stash_scope()` opens and closes the scope around each unit of work, so there's no window where a stale value can survive into the next one.

**[`django-request-cache`](https://github.com/anexia/django-request-cache)** takes the same idea a step further: instead of exposing one named value, it makes the *whole request object* reachable from anywhere first (via `django-userforeignkey`'s `get_current_request()`), then hangs a cache off it as an attribute. That's an extra dependency, and a much bigger object made globally available than most call sites need. Stash's storage never holds `request` — only the specific values you chose to stash, by name.

**Django's cache framework** (`django.core.cache`) is still the right choice the moment a value needs to survive past one request — nothing here replaces it. The trade-off in the table above is the one to remember: reach for the cache framework when a value is shared across requests or processes, and put stash *in front of it* when the same value is read more than once inside a single request.

## Usage

### `get_or_set`

```python
import stash

def get_feature_flags():
    return stash.get_or_set("feature_flags", load_feature_flags_from_db)
```

- First call in a request: runs `load_feature_flags_from_db()`, stores the result, returns it.
- Later calls in the same request: returns the stored result. The loader is not called.
- After the request ends: the stored value is gone.

### `memoize`

Same thing, as a decorator:

```python
import stash

@stash.memoize
def get_exchange_rate(currency):
    return ExchangeRate.objects.get(currency=currency).rate
```

`get_exchange_rate("EUR")` and `get_exchange_rate("USD")` are remembered separately (the key is built from the arguments). Use `@stash.memoize(key="...")` for a fixed key that ignores arguments.

### `get`, `set`, `clear`

```python
stash.set("user_permissions", perms)
stash.get("user_permissions")            # -> perms, or None
stash.get("missing", default=[])         # -> []

stash.clear("user_permissions")          # forget one value
stash.clear()                            # forget everything stored here
```

`clear` is what you call after writing to the underlying data, so later reads in the same request see the new state:

```python
def update_site_settings(**changes):
    SiteSettings.objects.filter(pk=1).update(**changes)
    stash.clear("site_settings")
```

### Nested scopes

`stash_scope()` with no name uses the same default scope as `StashMiddleware` and `StashCommandMixin`. Nesting one inside the other does not wipe the outer values:

```python
class Command(stash.StashCommandMixin, BaseCommand):
    def handle(self, *args, **options):
        tenant = stash.get_or_set("tenant", load_tenant)
        for row in rows:
            with stash.stash_scope():
                # tenant is still visible here
                process(row)   # per-item memos live only in this block
        # tenant is still here; per-item memos are gone
```

Writes in the inner `with` stay there. Reads look in the inner block first, then the outer one. `clear("tenant")` forgets that key in both; `clear()` with no key only forgets what the inner block stored.

### Named scopes

A name is a separate namespace that can be open at the same time as the default — so a package can stash `"tenant"` without colliding with the app's `"tenant"`.

If your package is the only opener, the [Install](#install) example is enough: no name, no `scope=`. Use a named scope when the project already has a default scope (or another package might) and you want your keys kept apart:

```python
import stash

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with stash.stash_scope("tenants"):
            stash.set(
                "tenant",
                Tenant.objects.get(domain=request.get_host()),
                scope="tenants",
            )
            return self.get_response(request)


def get_current_tenant():
    return stash.get("tenant", scope="tenants")
```

`stash.get("tenant")` still reads the default scope. Pass `scope=` at every call site that belongs to the named one, including `@stash.memoize(scope="tenants")`. Pick a stable name — the package name is fine.

### Outside a request

Nothing is stored unless a scope is open. In a management command, Celery task, or shell:

```python
stash.get_or_set("k", loader)   # just calls loader() every time
stash.set("k", value)           # does nothing
stash.get("k")                  # -> None
```

That is deliberate: a long-lived worker never accumulates stale values by accident.

For a management command, mix in `StashCommandMixin` so each run gets a scope — the same idea as `StashMiddleware` for HTTP. See [Install](#install). Per-item memos go in a nested `stash_scope()` as in [Nested scopes](#nested-scopes). In a Celery task or shell, open the scope yourself:

```python
with stash.stash_scope():
    process_item()
```

## Behaviour in one table

| Situation | `get_or_set("k", loader)` |
|-----------|---------------------------|
| Inside a request, first call | runs `loader()`, stores, returns |
| Inside a request, later call | returns stored value |
| After `stash.clear("k")` | runs `loader()` again |
| Different request | runs `loader()` again |
| Different thread / process | runs `loader()` again |
| No scope | runs `loader()` every time; stores nothing |

## Notes

- Values are stored and returned as **shallow copies**. Mutating what you get back does not change what is stored. Don't rely on identity.
- Stash is an L1 in front of whatever you already do. If you also want cross-process sharing, keep using Django's cache as L2 inside your loader.
- Works under WSGI and ASGI, with sync or async views. The middleware is sync- and async-capable, so it does not force Django to adapt the rest of the chain. Storage is `asgiref.local.Local`.

## Development

```bash
cd django-stash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[testing,development]"
python testmanage.py test
```
