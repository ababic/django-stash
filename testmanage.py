#!/usr/bin/env python

import argparse
import os
import shutil
import sys
import warnings

from django.core.management import execute_from_command_line


os.environ["DJANGO_SETTINGS_MODULE"] = "testapp.settings"
sys.path.append("tests")


def make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--deprecation",
        choices=["all", "pending", "imminent", "none"],
        default="imminent",
    )
    return parser


def parse_args(args=None):
    return make_parser().parse_known_args(args)


def runtests():
    args, rest = parse_args()

    only_django = r"^django(\.|$)"
    if args.deprecation == "all":
        warnings.simplefilter("default", DeprecationWarning)
        warnings.simplefilter("default", PendingDeprecationWarning)
    elif args.deprecation == "pending":
        warnings.filterwarnings(
            "default", category=DeprecationWarning, module=only_django
        )
        warnings.filterwarnings(
            "default", category=PendingDeprecationWarning, module=only_django
        )
    elif args.deprecation == "imminent":
        warnings.filterwarnings(
            "default", category=DeprecationWarning, module=only_django
        )
    elif args.deprecation == "none":
        pass

    argv = [sys.argv[0], *rest]
    if rest and rest[0] == "test":
        has_label = any(
            (not arg.startswith("-") and not arg.isdigit()) for arg in rest[1:]
        )
        if not has_label:
            argv.append("tests")

    try:
        execute_from_command_line(argv)
    finally:
        from django.conf import settings

        for attr in ("STATIC_ROOT", "MEDIA_ROOT"):
            path = getattr(settings, attr, None)
            if path:
                shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    runtests()
