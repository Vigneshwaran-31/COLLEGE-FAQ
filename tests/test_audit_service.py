"""
Tests for immutable audit logging, filtering, and safe CSV export with formula injection defense.
"""
from audit_service import (
    log_event,
    get_audit_logs,
    export_audit_logs_csv,
    sanitize_csv_cell
)


def test_audit_log_append_and_filtering(test_db_path, admin_user, student1_user):
    log_event(
        action="TEST_ACTION_INFO",
        actor_id=admin_user["id"],
        actor_username=admin_user["username"],
        actor_role="admin",
        details="Standard info event",
        severity="INFO",
        db_path=test_db_path
    )
    log_event(
        action="TEST_ACTION_SECURITY",
        actor_id=student1_user["id"],
        actor_username=student1_user["username"],
        actor_role="student",
        details="Security event",
        severity="SECURITY",
        db_path=test_db_path
    )

    all_logs = get_audit_logs(db_path=test_db_path)
    assert len(all_logs) >= 2

    # Filter by severity
    sec_logs = get_audit_logs(filter_severity="SECURITY", db_path=test_db_path)
    for l in sec_logs:
        assert l["severity"] == "SECURITY"

    # Filter by action keyword
    act_logs = get_audit_logs(filter_action="TEST_ACTION_INFO", db_path=test_db_path)
    assert len(act_logs) >= 1
    assert act_logs[0]["action"] == "TEST_ACTION_INFO"


def test_csv_formula_injection_defense():
    # Dangerous formula inputs
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-5+2") == "'-5+2"
    assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell("Normal String") == "Normal String"

    sample_logs = [
        {
            "id": 1,
            "timestamp": "2026-10-09 10:00:00",
            "actor_id": 2,
            "actor_username": "=cmd|' /C calc'!A0",
            "actor_role": "student",
            "action": "+EVIL_ACTION",
            "target_entity": "users",
            "target_id": "1",
            "details": "Formula injection payload",
            "severity": "WARNING",
            "ip_address": "127.0.0.1"
        }
    ]
    csv_str = export_audit_logs_csv(sample_logs)
    assert "'=cmd|" in csv_str
    assert "'+EVIL_ACTION" in csv_str
