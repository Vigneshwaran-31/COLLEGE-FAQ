"""
Tests for database schema initialization, seed data, and transaction management.
"""
from database import get_db_connection, hash_password


def test_init_db_creates_tables_and_seeds(test_db_path):
    with get_db_connection(test_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = set(r[0] for r in cursor.fetchall())

        expected_tables = {
            "users", "documents", "document_chunks", "faq_inquiries",
            "document_requests", "approval_actions", "email_queue", "audit_logs"
        }
        for tbl in expected_tables:
            assert tbl in tables, f"Expected table {tbl} was not created"

        # Check default seeded users
        cursor.execute("SELECT username, role FROM users ORDER BY id ASC;")
        users = cursor.fetchall()
        assert len(users) >= 3
        usernames = [u[0] for u in users]
        assert "admin" in usernames
        assert "student1" in usernames
        assert "student2" in usernames


def test_password_hashing():
    pwd = "SecretPassword123"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex length
    assert hash_password("DifferentPassword") != h1
