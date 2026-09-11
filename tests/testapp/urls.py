from django.http import HttpResponse
from django.urls import path

import stash


def probe_view(request):
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return ["ok"]

    first = stash.get_or_set("probe", loader)
    second = stash.get_or_set("probe", loader)
    return HttpResponse(f"calls={calls['n']};same={first == second}")


urlpatterns = [
    path("probe/", probe_view, name="probe"),
]
