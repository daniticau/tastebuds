import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip integration tests when no database URL is configured."""
    if os.getenv("TASTEBUDS_DATABASE_URL"):
        return

    skip_integration = pytest.mark.skip(reason="TASTEBUDS_DATABASE_URL not set")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
