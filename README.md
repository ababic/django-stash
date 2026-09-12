# django-stash

[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Remember a value for the rest of the current request, and read it back from anywhere — without passing `request` around.

```python
import stash

def get_current_tenant():
    return stash.get_or_set("tenant", lambda: Tenant.objects.get(pk=...))
```

Call it ten times in one request: the loader runs once. Next request: it runs again.

This is **not** a cache backend. Nothing is shared between requests, processes, or workers. Values live only while a request is being handled, and are thrown away when it finishes.

## Install

```bash
pip install django-stash
```

```python
MIDDLEWARE = [
    "stash.middleware.StashMiddleware",
    # ...
]
```

No `INSTALLED_APPS` entry needed.

## The problem it solves

You have something that is expensive to compute, and needed in several unrelated places during one request — a template tag, a model method, a serializer, a signal handler:

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
stash.clear()                            # forget everything for this request
```

`clear` is what you call after writing to the underlying data, so later reads in the same request see the new state:

```python
def update_site_settings(**changes):
    SiteSettings.objects.filter(pk=1).update(**changes)
    stash.clear("site_settings")
```

### Outside a request

Nothing is stored unless a scope is open. In a management command, Celery task, or shell:

```python
stash.get_or_set("k", loader)   # just calls loader() every time
stash.set("k", value)           # does nothing
stash.get("k")                  # -> None
```

That is deliberate: a long-lived worker never accumulates stale values by accident.

If you want the same per-unit-of-work behaviour there, open a scope yourself:

```python
with stash.stash_scope():
    process_batch()   # values remembered for this block only
```

## Behaviour in one table

| Situation | `get_or_set("k", loader)` |
|-----------|---------------------------|
| Inside a request, first call | runs `loader()`, stores, returns |
| Inside a request, later call | returns stored value |
| After `stash.clear("k")` | runs `loader()` again |
| Different request | runs `loader()` again |
| Different thread / process | runs `loader()` again |
| No middleware / no scope | runs `loader()` every time; stores nothing |

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
