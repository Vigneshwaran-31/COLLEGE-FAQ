"""
Tests for Human-in-the-Loop approval enforcement, agent self-approval prevention,
payload tampering detection, and email approval gates.
"""
import pytest
from auth_service import AuthorizationError
from approval_service import (
    create_approval_request,
    approve_action,
    reject_action,
    queue_email_for_approval,
    get_pending_approvals,
    ApprovalError
)
from database import get_db_connection


def test_ai_agent_cannot_approve_action(test_db_path, student1_user):
    app_id = create_approval_request(
        action_type="KB_PUBLISH",
        target_entity="documents",
        target_id=1,
        payload={"doc_id": 1},
        requested_by_user_id=student1_user["id"],
        requested_by_username=student1_user["username"],
        db_path=test_db_path
    )

    # Non-admin / student attempting approval MUST fail
    with pytest.raises(AuthorizationError):
        approve_action(app_id, student1_user, db_path=test_db_path)


def test_payload_tamper_detection(test_db_path, admin_user):
    original_payload = {"setting": "standard_policy", "fee": 1000}
    app_id = create_approval_request(
        action_type="CONFIG_CHANGE",
        target_entity="system_config",
        target_id=1,
        payload=original_payload,
        requested_by_user_id=admin_user["id"],
        requested_by_username=admin_user["username"],
        db_path=test_db_path
    )

    # Attempt to approve with altered payload
    tampered_payload = {"setting": "standard_policy", "fee": 999999}
    ok, msg = approve_action(
        app_id, admin_user,
        current_payload=tampered_payload,
        db_path=test_db_path
    )
    # MUST be aborted due to payload hash mismatch
    assert ok is False
    assert "modified" in msg.lower() or "aborted" in msg.lower()


def test_email_approval_enforcement(test_db_path, student1_user, admin_user):
    # Student requests official email delivery
    email_id = queue_email_for_approval(
        recipient="sponsor@external.org",
        subject="Bonafide Verification Notification",
        body="Please find attached the official verification.",
        requested_by_user_id=student1_user["id"],
        requested_by_username=student1_user["username"],
        db_path=test_db_path
    )

    # Email must be PENDING_APPROVAL and NOT sent yet
    with get_db_connection(test_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, sent_at FROM email_queue WHERE id = ?", (email_id,))
        row = cursor.fetchone()
        assert row["status"] == "PENDING_APPROVAL"
        assert row["sent_at"] is None

    # Retrieve approval
    pending = get_pending_approvals(db_path=test_db_path)
    email_apps = [a for a in pending if a["target_entity"] == "email_queue" and a["target_id"] == email_id]
    assert len(email_apps) == 1
    app_id = email_apps[0]["id"]

    # When approved, if SMTP is not configured in test, reports unavailable rather than simulating success!
    ok, msg = approve_action(app_id, admin_user, review_notes="Approved email draft", db_path=test_db_path)
    # SMTP is disabled by default in test environment
    assert "unavailable" in msg.lower() or "sent" in msg.lower() or "smtp" in msg.lower()

    with get_db_connection(test_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM email_queue WHERE id = ?", (email_id,))
        status = cursor.fetchone()["status"]
        assert status in ("FAILED", "SENT")  # Never silently left pending without real result
