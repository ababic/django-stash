from django.http import HttpResponse
from django.urls import path

import stash


def _probe():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return ["ok"]

    first = stash.get_or_set("probe", loader)
    second = stash.get_or_set("probe", loader)
    return HttpResponse(f"calls={calls['n']};same={first == second}")


def probe_view(request):
    return _probe()


async def async_probe_view(request):
    return _probe()


urlpatterns = [
    path("probe/", probe_view, name="probe"),
    path("async-probe/", async_probe_view, name="async_probe"),
]
