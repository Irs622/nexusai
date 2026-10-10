"""
Setuptools shim for legacy editable installs.

All package metadata (name, version, packages, entry points) lives in
``pyproject.toml``; this file intentionally declares nothing.
"""

from setuptools import setup

setup()
