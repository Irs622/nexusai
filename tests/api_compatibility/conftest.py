"""
Pytest configuration for API compatibility snapshot test suite.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --update-snapshots option to pytest CLI."""
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Update golden API compatibility snapshot files on disk",
    )
