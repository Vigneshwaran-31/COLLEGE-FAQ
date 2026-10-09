"""
Authentication and Authorization Service for DUM DUM Group of Institution.
Provides credential validation, role checking, student registration, and backend access enforcement.
"""
import re
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from database import get_db_connection, hash_password
from audit_service import log_event


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class AuthorizationError(Exception):
    """Raised when access control check fails."""
    pass


def authenticate(
    username: str,
    password: str,
    ip_address: str = "127.0.0.1",
    db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Validates user credentials against stored SHA-256 password hash.
    Records security audit log for both success and failure.
    """
    clean_username = username.strip()
    if not clean_username or not password:
        return None

    pwd_hash = hash_password(password)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (clean_username,))
        row = cursor.fetchone()

        if row and row["password_hash"] == pwd_hash:
            user = dict(row)
            del user["password_hash"]
            log_event(
                action="USER_LOGIN_SUCCESS",
                actor_id=user["id"],
                actor_username=user["username"],
                actor_role=user["role"],
                target_entity="users",
                target_id=str(user["id"]),
                details=f"Successful login as {user['role']}",
                severity="INFO",
                ip_address=ip_address,
                db_path=db_path,
                conn=conn
            )
            return user
        else:
            log_event(
                action="USER_LOGIN_FAILURE",
                actor_username=clean_username,
                actor_role="unknown",
                target_entity="users",
                details=f"Failed login attempt for username: {clean_username}",
                severity="WARNING",
                ip_address=ip_address,
                db_path=db_path,
                conn=conn
            )
            return None


def register_student(
    username: str,
    password: str,
    full_name: str,
    roll_number: str,
    department: str,
    year_semester: str,
    email: str,
    db_path: Optional[Path] = None,
) -> Tuple[bool, str, Optional[int]]:
    """
    Registers a new student account with validation.
    Enforces password length and roll number format.
    """
    username = username.strip()
    full_name = full_name.strip()
    roll_number = roll_number.strip().upper()
    email = email.strip().lower()

    if len(username) < 3:
        return False, "Username must be at least 3 characters long.", None
    if len(password) < 6:
        return False, "Password must be at least 6 characters long.", None
    if not full_name:
        return False, "Full name is required.", None
    if not roll_number:
        return False, "Roll / Registration number is required.", None
    if not email or "@" not in email:
        return False, "A valid email address is required.", None

    pwd_hash = hash_password(password)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return False, f"Username '{username}' is already taken.", None

        # Check if roll number exists
        cursor.execute("SELECT id FROM users WHERE roll_number = ?", (roll_number,))
        if cursor.fetchone():
            return False, f"Roll number '{roll_number}' is already registered.", None

        cursor.execute("""
            INSERT INTO users (username, password_hash, role, full_name, roll_number, department, year_semester, email)
            VALUES (?, ?, 'student', ?, ?, ?, ?, ?)
        """, (username, pwd_hash, full_name, roll_number, department, year_semester, email))

        new_id = cursor.lastrowid
        log_event(
            action="STUDENT_REGISTERED",
            actor_id=new_id,
            actor_username=username,
            actor_role="student",
            target_entity="users",
            target_id=str(new_id),
            details=f"New student registration for {full_name} ({roll_number})",
            severity="AUDIT",
            db_path=db_path,
            conn=conn
        )
        return True, "Student registration successful! You can now log in.", new_id


def get_user_by_id(user_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a sanitized user dictionary by ID."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        user = dict(row)
        if "password_hash" in user:
            del user["password_hash"]
        return user


def require_admin(user: Optional[Dict[str, Any]]):
    """
    Enforces that the user is an authenticated administrator.
    Raises AuthorizationError if check fails.
    """
    if not user or user.get("role") != "admin":
        raise AuthorizationError("Access denied: Administrative privileges required.")


def require_student(user: Optional[Dict[str, Any]]):
    """
    Enforces that the user is an authenticated student.
    Raises AuthorizationError if check fails.
    """
    if not user or user.get("role") != "student":
        raise AuthorizationError("Access denied: Student access required.")


def verify_student_isolation(user: Optional[Dict[str, Any]], target_student_id: int):
    """
    Strictly prevents student A from accessing student B's records.
    Admins are permitted to inspect any student's records.
    """
    if not user:
        raise AuthorizationError("Authentication required.")
    if user.get("role") == "admin":
        return  # Admin access permitted
    if user.get("id") != target_student_id:
        raise AuthorizationError("Access denied: You are not authorized to view or modify records belonging to another student.")
