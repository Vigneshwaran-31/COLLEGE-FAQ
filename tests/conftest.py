import pytest
import tempfile
import os
import sys
from pathlib import Path

# Ensure root directory is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db, get_db_connection
from auth_service import authenticate, get_user_by_id


@pytest.fixture
def test_db_path(tmp_path):
    """Provides a fresh isolated SQLite database path for tests."""
    db_file = tmp_path / "test_college_faq.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def admin_user(test_db_path):
    """Provides authenticated admin user dict."""
    user = authenticate("admin", "Admin@123", db_path=test_db_path)
    assert user is not None
    return user


@pytest.fixture
def student1_user(test_db_path):
    """Provides authenticated student 1 user dict."""
    user = authenticate("student1", "Student@123", db_path=test_db_path)
    assert user is not None
    return user


@pytest.fixture
def student2_user(test_db_path):
    """Provides authenticated student 2 user dict."""
    user = authenticate("student2", "Student@123", db_path=test_db_path)
    assert user is not None
    return user
