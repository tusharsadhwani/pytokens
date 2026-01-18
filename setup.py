from __future__ import annotations

import os
import platform

from setuptools import setup


if "PYTOKENS_USE_MYPYC" in os.environ:
    USE_MYPYC = os.environ["PYTOKENS_USE_MYPYC"] == "1"
else:
    USE_MYPYC = platform.python_implementation() == "CPython"


def get_ext_modules():
    if not USE_MYPYC:
        return []

    from mypyc.build import mypycify
    return mypycify(
        [
            "src/pytokens/__init__.py",
            "src/pytokens/_mypyc_dummy.py",
        ],
        opt_level="3",
    )


setup(ext_modules=get_ext_modules())
