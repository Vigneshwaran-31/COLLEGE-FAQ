"""
Tests for authentication, registration validation, and student access isolation.
"""
import pytest
from auth_service import (
    authenticate,
    register_student,
    require_admin,
    require_student,
    verify_student_isolation,
    AuthorizationError
)


def test_authentication_success_and_failure(test_db_path):
    admin = authenticate("admin", "Admin@123", db_path=test_db_path)
    assert admin is not None
    assert admin["role"] == "admin"
    assert "password_hash" not in admin

    student = authenticate("student1", "Student@123", db_path=test_db_path)
    assert student is not None
    assert student["role"] == "student"

    # Invalid password
    bad = authenticate("admin", "WrongPassword", db_path=test_db_path)
    assert bad is None

    # Non-existent user
    nobody = authenticate("ghost_user", "AnyPassword", db_path=test_db_path)
    assert nobody is None


def test_student_registration_validation(test_db_path):
    # Valid registration
    ok, msg, uid = register_student(
        username="new_student",
        password="ValidPassword123",
        full_name="Ananya Roy",
        roll_number="DGD/2026/CSE-101",
        department="Computer Science & Engineering",
        year_semester="1st Year / 1st Sem",
        email="ananya@dumdumgroup.edu",
        db_path=test_db_path
    )
    assert ok is True
    assert uid is not None

    # Duplicate username
    dup_ok, dup_msg, _ = register_student(
        username="new_student",
        password="ValidPassword123",
        full_name="Duplicate Name",
        roll_number="DGD/2026/CSE-102",
        department="CSE",
        year_semester="1st Year",
        email="dup@dumdumgroup.edu",
        db_path=test_db_path
    )
    assert dup_ok is False
    assert "already taken" in dup_msg

    # Short password
    short_ok, short_msg, _ = register_student(
        username="another_student",
        password="123",
        full_name="Short Pass",
        roll_number="DGD/2026/CSE-103",
        department="CSE",
        year_semester="1st Year",
        email="short@dumdumgroup.edu",
        db_path=test_db_path
    )
    assert short_ok is False
    assert "at least 6 characters" in short_msg


def test_role_enforcement_and_student_isolation(test_db_path, admin_user, student1_user, student2_user):
    # Admin check
    require_admin(admin_user)
    with pytest.raises(AuthorizationError):
        require_admin(student1_user)

    # Student check
    require_student(student1_user)
    with pytest.raises(AuthorizationError):
        require_student(admin_user)

    # Student isolation check: Student 1 can access own data
    verify_student_isolation(student1_user, student1_user["id"])

    # Student 1 CANNOT access Student 2 data
    with pytest.raises(AuthorizationError):
        verify_student_isolation(student1_user, student2_user["id"])

    # Admin CAN access any student's data
    verify_student_isolation(admin_user, student1_user["id"])
    verify_student_isolation(admin_user, student2_user["id"])
