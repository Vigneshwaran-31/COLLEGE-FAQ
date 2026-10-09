"""
Tests for student document requests, draft invalidation, ReportLab PDF generation, and secure downloads.
"""
import pytest
from pathlib import Path
from auth_service import AuthorizationError
from document_service import (
    create_document_request,
    get_student_document_requests,
    get_request_by_id,
    update_request_draft,
    generate_approved_pdf_for_request,
    get_secure_pdf_path,
    DocumentServiceError
)
from approval_service import approve_action, reject_action, get_pending_approvals


def test_create_document_request_and_pending_status(test_db_path, student1_user):
    req = create_document_request(
        student_user=student1_user,
        doc_type="BONAFIDE",
        purpose="Passport verification appointment",
        supporting_notes="Urgent processing requested",
        db_path=test_db_path
    )
    assert req["request_number"].startswith("DOC-2026-")
    assert req["status"] == "PENDING_APPROVAL"
    assert req["pdf_path"] is None
    assert req["content_hash"] is not None

    # Check student request listing
    my_requests = get_student_document_requests(student1_user["id"], db_path=test_db_path)
    assert len(my_requests) == 1
    assert my_requests[0]["id"] == req["id"]


def test_approved_request_generates_pdf_and_rejected_never_generates(test_db_path, student1_user, admin_user):
    # 1. Create request
    req = create_document_request(
        student_user=student1_user,
        doc_type="STUDY_CERTIFICATE",
        purpose="Bank education loan application",
        db_path=test_db_path
    )
    req_id = req["id"]

    # Pending request MUST NOT allow PDF download
    with pytest.raises(DocumentServiceError, match="Must be 'APPROVED'"):
        get_secure_pdf_path(req_id, student1_user, db_path=test_db_path)

    # Find corresponding HITL approval
    pending = get_pending_approvals(db_path=test_db_path)
    doc_approvals = [a for a in pending if a["target_entity"] == "document_requests" and a["target_id"] == req_id]
    assert len(doc_approvals) == 1
    approval_id = doc_approvals[0]["id"]

    # 2. Admin approves action -> triggers PDF generation
    ok, msg = approve_action(approval_id, admin_user, review_notes="Verified student record", db_path=test_db_path)
    assert ok is True

    # Verify request updated to APPROVED and PDF exists
    approved_req = get_request_by_id(req_id, db_path=test_db_path)
    assert approved_req["status"] == "APPROVED"
    assert approved_req["pdf_path"] is not None
    assert Path(approved_req["pdf_path"]).exists()

    # Owner student can download PDF
    pdf_path = get_secure_pdf_path(req_id, student1_user, db_path=test_db_path)
    assert pdf_path.exists()

    # 3. Test rejected request NEVER generates PDF
    req2 = create_document_request(
        student_user=student1_user,
        doc_type="PERMISSION_LETTER",
        purpose="Invalid unauthorized event",
        db_path=test_db_path
    )
    pending2 = get_pending_approvals(db_path=test_db_path)
    app2 = [a for a in pending2 if a["target_id"] == req2["id"]][0]

    reject_action(app2["id"], admin_user, reason="Unauthorized purpose", db_path=test_db_path)

    rejected_req = get_request_by_id(req2["id"], db_path=test_db_path)
    assert rejected_req["status"] == "REJECTED"
    assert rejected_req["pdf_path"] is None

    # Cannot download rejected request PDF
    with pytest.raises(DocumentServiceError, match="Must be 'APPROVED'"):
        get_secure_pdf_path(req2["id"], student1_user, db_path=test_db_path)


def test_approval_invalidation_after_content_change(test_db_path, student1_user, admin_user):
    # Create request and approve it
    req = create_document_request(
        student_user=student1_user,
        doc_type="BONAFIDE",
        purpose="Visa appointment",
        db_path=test_db_path
    )
    generate_approved_pdf_for_request(req["id"], admin_user, db_path=test_db_path)

    approved_req = get_request_by_id(req["id"], db_path=test_db_path)
    assert approved_req["status"] == "APPROVED"

    # Now modify draft content
    updated_req = update_request_draft(
        request_id=req["id"],
        new_draft_content="Altered draft content with modified dates.",
        editor_user=student1_user,
        db_path=test_db_path
    )

    # CRITICAL CHECK: Status MUST revert to PENDING_APPROVAL and pdf_path MUST be cleared
    assert updated_req["status"] == "PENDING_APPROVAL"
    assert updated_req["pdf_path"] is None
    assert updated_req["approved_by"] is None


def test_student_pdf_download_isolation(test_db_path, student1_user, student2_user, admin_user):
    req = create_document_request(
        student_user=student1_user,
        doc_type="BONAFIDE",
        purpose="Concession bus pass",
        db_path=test_db_path
    )
    generate_approved_pdf_for_request(req["id"], admin_user, db_path=test_db_path)

    # Student 1 (owner) can download
    p1 = get_secure_pdf_path(req["id"], student1_user, db_path=test_db_path)
    assert p1.exists()

    # Admin can download
    p_admin = get_secure_pdf_path(req["id"], admin_user, db_path=test_db_path)
    assert p_admin.exists()

    # Student 2 CANNOT download Student 1's certificate!
    with pytest.raises(AuthorizationError):
        get_secure_pdf_path(req["id"], student2_user, db_path=test_db_path)
