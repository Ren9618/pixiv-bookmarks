"""Shared test configuration.

The application reads ``DATA_DIR`` at import time, so point it at a temporary
directory before any ``pixivapp`` module is imported.  The autouse fixture
clears that directory between tests; real credentials are never touched.
"""

import os
import shutil
import tempfile
from pathlib import Path

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="pixiv-stack-tests-"))

os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["VIEWER_PASSWORD"] = ""
os.environ["VIEWER_SECRET"] = "test-secret-not-for-production"
os.environ["SYNC_INTERVAL_MINUTES"] = "15"

import pytest  # noqa: E402  (environment must be set first)


@pytest.fixture(autouse=True)
def clean_data_dir():
    """Give every test an empty data directory."""
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for child in TEST_DATA_DIR.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    yield
