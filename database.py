"""
Database models, initialization, migrations, and connection helpers for DUM DUM Group of Institution.
Uses SQLite for robust, zero-configuration local persistence.
"""
import sqlite3
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import DATABASE_PATH, PASSWORD_SALT


def get_db_path() -> Path:
    return DATABASE_PATH


@contextmanager
def get_db_connection(db_path: Optional[Path] = None):
    """Context manager for SQLite database connection with row factory, foreign keys, and WAL mode."""
    target_path = db_path or get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def hash_password(password: str, salt: str = PASSWORD_SALT) -> str:
    """Hashes a password with salt using SHA-256."""
    salted = f"{salt}:{password}:{salt}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def init_db(db_path: Optional[Path] = None):
    """Creates tables, indexes, and initial default users if they do not exist."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'admin')),
                full_name TEXT NOT NULL,
                roll_number TEXT,
                department TEXT,
                year_semester TEXT,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Documents Table (Official & Pending Knowledge Base)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                uploaded_by INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PENDING_REVIEW', 'PUBLISHED', 'UNPUBLISHED', 'REPLACED')),
                version INTEGER DEFAULT 1,
                previous_version_id INTEGER,
                page_count INTEGER DEFAULT 1,
                summary TEXT,
                topics TEXT,
                extracted_rules TEXT,
                important_dates TEXT,
                verified_by INTEGER,
                verified_at TIMESTAMP,
                FOREIGN KEY (uploaded_by) REFERENCES users(id),
                FOREIGN KEY (verified_by) REFERENCES users(id),
                FOREIGN KEY (previous_version_id) REFERENCES documents(id)
            );
        """)

        # 3. Document Chunks Table (For RAG Search)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                heading TEXT,
                content TEXT NOT NULL,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
        """)

        # 4. Student FAQ Inquiries Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS faq_inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                category TEXT,
                answer TEXT NOT NULL,
                verification_status TEXT NOT NULL CHECK(verification_status IN ('VERIFIED_OFFICIAL', 'PARTIALLY_VERIFIED', 'UNVERIFIED')),
                sources_json TEXT,
                agent_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id)
            );
        """)

        # 5. Document Requests Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                request_number TEXT UNIQUE NOT NULL,
                doc_type TEXT NOT NULL,
                student_name TEXT NOT NULL,
                roll_number TEXT NOT NULL,
                department TEXT NOT NULL,
                year_semester TEXT NOT NULL,
                purpose TEXT NOT NULL,
                supporting_notes TEXT,
                draft_content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CHANGES_REQUESTED')),
                admin_feedback TEXT,
                approved_by INTEGER,
                approved_at TIMESTAMP,
                pdf_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id),
                FOREIGN KEY (approved_by) REFERENCES users(id)
            );
        """)

        # 6. Human-in-the-Loop Approval Actions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                payload_hash TEXT NOT NULL,
                requested_by INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED')),
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                review_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (requested_by) REFERENCES users(id),
                FOREIGN KEY (reviewed_by) REFERENCES users(id)
            );
        """)

        # 7. Email Queue Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                approval_id INTEGER,
                status TEXT NOT NULL CHECK(status IN ('PENDING_APPROVAL', 'APPROVED', 'SENT', 'FAILED', 'REJECTED')),
                sent_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (approval_id) REFERENCES approval_actions(id)
            );
        """)

        # 8. Audit Logs Table (Append-only)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actor_id INTEGER,
                actor_username TEXT,
                actor_role TEXT,
                action TEXT NOT NULL,
                target_entity TEXT,
                target_id TEXT,
                details TEXT,
                severity TEXT DEFAULT 'INFO' CHECK(severity IN ('INFO', 'WARNING', 'SECURITY', 'AUDIT')),
                ip_address TEXT
            );
        """)

        # Create Indexes for Search Performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON document_chunks(document_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_faq_student ON faq_inquiries(student_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_requests_student ON document_requests(student_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_requests_status ON document_requests(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_id);")

        # Seed Default Users if empty
        cursor.execute("SELECT COUNT(*) FROM users;")
        if cursor.fetchone()[0] == 0:
            seed_default_users(cursor)


def seed_default_users(cursor: sqlite3.Cursor):
    """Seeds initial administrative and student accounts for DUM DUM Group of Institution."""
    users = [
        (
            "admin",
            hash_password("Admin@123"),
            "admin",
            "Dr. Alok Banerjee (Registrar)",
            "ADMIN-01",
            "Administration",
            "Staff",
            "registrar@dumdumgroup.edu"
        ),
        (
            "student1",
            hash_password("Student@123"),
            "student",
            "Rahul Sharma",
            "DGD/2024/CSE-042",
            "Computer Science & Engineering",
            "3rd Year / 5th Sem",
            "rahul.cse@dumdumgroup.edu"
        ),
        (
            "student2",
            hash_password("Student@123"),
            "student",
            "Priya Patel",
            "DGD/2024/ECE-018",
            "Electronics & Communication Engineering",
            "2nd Year / 3rd Sem",
            "priya.ece@dumdumgroup.edu"
        )
    ]
    cursor.executemany("""
        INSERT INTO users (username, password_hash, role, full_name, roll_number, department, year_semester, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, users)
