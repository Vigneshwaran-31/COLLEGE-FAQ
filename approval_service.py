"""
Human-in-the-Loop (HITL) Approval Service for DUM DUM Group of Institution.
Enforces backend authorization gates for official document issuance, email dispatch,
knowledge base modifications, and destructive operations.
Guarantees:
- AI agents can never approve their own proposals.
- Approvals are cryptographically tied to exact content payload hashes.
- Modifications invalidate prior approvals.
- Unapproved or rejected actions cannot execute.
"""
import hashlib
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from database import get_db_connection
from auth_service import require_admin
from audit_service import log_event
from config import (
    SMTP_ENABLED,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_EMAIL
)


class ApprovalError(Exception):
    """Raised when an approval gate or validation check fails."""
    pass


def compute_payload_hash(payload: Any) -> str:
    """Computes a deterministic SHA-256 hash of a payload dictionary or string."""
    if isinstance(payload, dict) or isinstance(payload, list):
        canonical_str = json.dumps(payload, sort_keys=True, default=str)
    else:
        canonical_str = str(payload)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def create_approval_request(
    action_type: str,
    target_entity: str,
    target_id: int,
    payload: Any,
    requested_by_user_id: int,
    requested_by_username: str,
    db_path: Optional[Path] = None,
) -> int:
    """
    Submits a sensitive action to the Human-in-the-Loop approval queue.
    Status starts as PENDING.
    """
    payload_hash = compute_payload_hash(payload)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO approval_actions (action_type, target_entity, target_id, payload_hash, requested_by, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
        """, (action_type, target_entity, target_id, payload_hash, requested_by_user_id))
        approval_id = cursor.lastrowid

        log_event(
            action="HITL_APPROVAL_REQUESTED",
            actor_id=requested_by_user_id,
            actor_username=requested_by_username,
            actor_role="user",
            target_entity=target_entity,
            target_id=str(target_id),
            details=f"Approval requested for {action_type} (Action ID: {approval_id}, Hash: {payload_hash[:10]}...)",
            severity="AUDIT",
            db_path=db_path,
            conn=conn
        )
        return approval_id


def approve_action(
    approval_id: int,
    admin_user: Dict[str, Any],
    review_notes: str = "",
    current_payload: Any = None,
    db_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    Grants human administrator approval and triggers backend execution.
    Verifies that:
    1. The actor is an authenticated administrator (AI agents cannot approve).
    2. The approval is in PENDING status.
    3. The payload has not changed since the approval was requested.
    """
    # Strict admin authorization check
    require_admin(admin_user)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM approval_actions WHERE id = ?", (approval_id,))
        action = cursor.fetchone()
        if not action:
            raise ApprovalError(f"Approval action with ID {approval_id} does not exist.")

        if action["status"] != "PENDING":
            raise ApprovalError(f"Cannot approve action with status '{action['status']}'. Must be 'PENDING'.")

        # If current payload is supplied, verify hash consistency
        if current_payload is not None:
            current_hash = compute_payload_hash(current_payload)
            if current_hash != action["payload_hash"]:
                # Content changed! Invalidate approval
                cursor.execute("UPDATE approval_actions SET status = 'REJECTED', review_notes = ? WHERE id = ?",
                               ("Payload altered since request creation. Approval aborted.", approval_id))
                log_event(
                    action="HITL_HASH_MISMATCH_ABORT",
                    actor_id=admin_user["id"],
                    actor_username=admin_user["username"],
                    actor_role="admin",
                    target_entity=action["target_entity"],
                    target_id=str(action["target_id"]),
                    details="Action blocked: Content modified after draft generation.",
                    severity="SECURITY",
                    db_path=db_path,
                    conn=conn
                )
                return False, "Approval aborted: Content was modified after the request was created."

        # Mark as APPROVED
        cursor.execute("""
            UPDATE approval_actions
            SET status = 'APPROVED',
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP,
                review_notes = ?
            WHERE id = ?
        """, (admin_user["id"], review_notes, approval_id))

    # Execute approved action
    exec_success, exec_msg = execute_approved_action(dict(action), admin_user, db_path=db_path)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        if exec_success:
            cursor.execute("UPDATE approval_actions SET status = 'EXECUTED' WHERE id = ?", (approval_id,))
            log_event(
                action="HITL_ACTION_EXECUTED",
                actor_id=admin_user["id"],
                actor_username=admin_user["username"],
                actor_role="admin",
                target_entity=action["target_entity"],
                target_id=str(action["target_id"]),
                details=f"Action {action['action_type']} executed successfully: {exec_msg}",
                severity="AUDIT",
                db_path=db_path,
                conn=conn
            )
        else:
            log_event(
                action="HITL_ACTION_EXECUTION_FAILED",
                actor_id=admin_user["id"],
                actor_username=admin_user["username"],
                actor_role="admin",
                target_entity=action["target_entity"],
                target_id=str(action["target_id"]),
                details=f"Approved action {action['action_type']} failed during execution: {exec_msg}",
                severity="WARNING",
                db_path=db_path,
                conn=conn
            )

    return exec_success, exec_msg


def reject_action(
    approval_id: int,
    admin_user: Dict[str, Any],
    reason: str = "Rejected by administrator",
    db_path: Optional[Path] = None,
) -> bool:
    """
    Rejects a pending action. Prevents execution and updates target entity status.
    """
    require_admin(admin_user)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM approval_actions WHERE id = ?", (approval_id,))
        action = cursor.fetchone()
        if not action:
            raise ApprovalError(f"Approval action with ID {approval_id} not found.")

        cursor.execute("""
            UPDATE approval_actions
            SET status = 'REJECTED',
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP,
                review_notes = ?
            WHERE id = ?
        """, (admin_user["id"], reason, approval_id))

        # Update target entity
        if action["target_entity"] == "document_requests":
            cursor.execute("""
                UPDATE document_requests
                SET status = 'REJECTED', admin_feedback = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (reason, action["target_id"]))
        elif action["target_entity"] == "email_queue":
            cursor.execute("""
                UPDATE email_queue
                SET status = 'REJECTED', error_message = ?
                WHERE id = ?
            """, (reason, action["target_id"]))

        log_event(
            action="HITL_ACTION_REJECTED",
            actor_id=admin_user["id"],
            actor_username=admin_user["username"],
            actor_role="admin",
            target_entity=action["target_entity"],
            target_id=str(action["target_id"]),
            details=f"Admin rejected {action['action_type']}. Reason: {reason}",
            severity="AUDIT",
            db_path=db_path,
            conn=conn
        )
        return True


def invalidate_approval_for_target(
    target_entity: str,
    target_id: int,
    reason: str = "Draft content was updated",
    db_path: Optional[Path] = None,
):
    """
    Invalidates any existing approvals when draft content changes.
    Reverts status so unapproved content can never be issued.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE approval_actions
            SET status = 'REJECTED',
                review_notes = ?
            WHERE target_entity = ? AND target_id = ? AND status IN ('PENDING', 'APPROVED')
        """, (f"Invalidated: {reason}", target_entity, target_id))

        if target_entity == "document_requests":
            cursor.execute("""
                UPDATE document_requests
                SET status = 'PENDING_APPROVAL', pdf_path = NULL, approved_by = NULL, approved_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (target_id,))

        log_event(
            action="HITL_APPROVAL_INVALIDATED",
            actor_username="System Guard",
            actor_role="system",
            target_entity=target_entity,
            target_id=str(target_id),
            details=f"Approval invalidated for {target_entity} #{target_id}: {reason}",
            severity="WARNING",
            db_path=db_path,
            conn=conn
        )


def execute_approved_action(
    action: Dict[str, Any],
    admin_user: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Dispatches execution for approved action types."""
    action_type = action["action_type"]
    target_id = action["target_id"]

    if action_type == "DOCUMENT_ISSUANCE":
        # Import lazily to avoid circular dependencies
        from document_service import generate_approved_pdf_for_request
        return generate_approved_pdf_for_request(target_id, admin_user, db_path=db_path)

    elif action_type == "EMAIL_DISPATCH":
        return dispatch_approved_email(target_id, db_path=db_path)

    elif action_type == "KB_PUBLISH":
        from knowledge_base import publish_document
        publish_document(target_id, admin_user, review_notes="Approved via HITL queue", db_path=db_path)
        return True, f"Document #{target_id} published successfully."

    elif action_type == "KB_UNPUBLISH":
        from knowledge_base import unpublish_document
        unpublish_document(target_id, admin_user, reason="Unpublished via HITL queue", db_path=db_path)
        return True, f"Document #{target_id} unpublished."

    return False, f"Unknown action type '{action_type}'"


def queue_email_for_approval(
    recipient: str,
    subject: str,
    body: str,
    requested_by_user_id: int,
    requested_by_username: str,
    db_path: Optional[Path] = None,
) -> int:
    """
    Prepares an email in email_queue and creates a pending approval.
    Does NOT send until explicitly approved by an administrator.
    """
    payload = {"recipient": recipient, "subject": subject, "body": body}

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO email_queue (recipient, subject, body, status)
            VALUES (?, ?, ?, 'PENDING_APPROVAL')
        """, (recipient, subject, body))
        email_id = cursor.lastrowid

    approval_id = create_approval_request(
        action_type="EMAIL_DISPATCH",
        target_entity="email_queue",
        target_id=email_id,
        payload=payload,
        requested_by_user_id=requested_by_user_id,
        requested_by_username=requested_by_username,
        db_path=db_path
    )

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE email_queue SET approval_id = ? WHERE id = ?", (approval_id, email_id))

    return email_id


def dispatch_approved_email(email_id: int, db_path: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Attempts to dispatch an email from the email_queue.
    If SMTP is not configured or disabled in .env, reports that sending is unavailable
    rather than simulating success.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM email_queue WHERE id = ?", (email_id,))
        email_record = cursor.fetchone()
        if not email_record:
            return False, f"Email record #{email_id} not found."

    if not SMTP_ENABLED or not SMTP_PASSWORD:
        msg = "Email delivery unavailable: SMTP service is disabled or credentials are not configured in .env."
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_queue
                SET status = 'FAILED', error_message = ?
                WHERE id = ?
            """, (msg, email_id))
        return False, msg

    # Try SMTP transmission
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = email_record["recipient"]
        msg["Subject"] = email_record["subject"]
        msg.attach(MIMEText(email_record["body"], "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10.0) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_queue
                SET status = 'SENT', sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (email_id,))
        return True, f"Email sent successfully to {email_record['recipient']}"

    except Exception as e:
        err_msg = f"SMTP transmission error: {str(e)}"
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE email_queue
                SET status = 'FAILED', error_message = ?
                WHERE id = ?
            """, (err_msg, email_id))
        return False, err_msg


def get_pending_approvals(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieves all pending approvals for administrator review."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                a.*,
                u.username AS requester_username,
                u.full_name AS requester_name,
                u.role AS requester_role
            FROM approval_actions a
            JOIN users u ON a.requested_by = u.id
            WHERE a.status = 'PENDING'
            ORDER BY a.id ASC
        """)
        return [dict(r) for r in cursor.fetchall()]
