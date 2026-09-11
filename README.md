# django-stash

[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD--3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Scoped ambient memoization for Django.

Stash values for the duration of a **request** (or any other explicit scope), and read them again from anywhere in the call stack — without threading a `request` through every helper.

This is **not** a cache backend. It does not replace Redis/Memcached/database cache. It is an L1 memo pad that only exists while a scope is open.

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

No `INSTALLED_APPS` entry required.

## Usage

```python
import stash

def expensive_site_paths():
    return stash.get_or_set(
        "wagtail.site_root_paths",
        loader=compute_site_root_paths,
    )

@stash.memoize(key="taxonomy.colours")
def get_colour_choices():
    return list(Colour.objects.values_list("id", "name"))
```

Outside a scope (management commands, Celery, shell), `get_or_set` / `memoize` just call the loader every time. Nothing sticks on the worker.

### Manual scopes

```python
with stash.stash_scope():
    ...
```

Useful for tests, management commands, or task bodies that want the same behaviour.

### Clearing

```python
stash.clear("wagtail.site_root_paths")  # one key
stash.clear()                           # everything in this scope
```

## Rules of thumb

1. **Scope owns lifetime** — middleware / `stash_scope()` enable at enter and disable in `finally`.
2. **No scope ⇒ no stash** — avoids sticky process caches on Gunicorn sync workers.
3. **Prefer immutable-ish values** — stash stores/returns shallow copies; don't stash live model graphs you plan to mutate in place.
4. **Shared cache is separate** — if you need cross-process invalidation, keep Django's cache as L2 and use stash as L1 in front of it.

## Development

```bash
cd django-stash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[testing,development]"
python testmanage.py test
```
