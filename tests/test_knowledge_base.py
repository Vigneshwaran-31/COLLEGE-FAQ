"""
Tests for Knowledge Base lifecycle, publishing gatekeeper, versioning, and grounded RAG search.
"""
import pytest
from pathlib import Path
from auth_service import AuthorizationError
from knowledge_base import (
    add_document,
    publish_document,
    unpublish_document,
    replace_document,
    search_published_knowledge_base,
    get_document_by_id,
    get_all_documents
)
from seed_sample_documents import generate_pdf_doc


def test_knowledge_base_publishing_gate(test_db_path, admin_user, student1_user, tmp_path):
    # 1. Create a dummy policy PDF
    pdf_path = generate_pdf_doc(
        "Special_Research_Policy.pdf",
        "Special Research Grant Policy",
        [("Section 1: Grant Allocation", "Students may apply for Rs. 50,000 innovation grant by October 15th.")]
    )

    # 2. Add document -> starts in PENDING_REVIEW
    doc = add_document(
        file_path=pdf_path,
        original_filename="Special_Research_Policy.pdf",
        title="Special Research Grant Policy",
        uploaded_by_user_id=admin_user["id"],
        uploaded_by_username=admin_user["username"],
        run_ai_analysis=False,
        db_path=test_db_path
    )
    assert doc["status"] == "PENDING_REVIEW"

    # CRITICAL CHECK: In PENDING_REVIEW, search MUST NOT return this document!
    search_pending = search_published_knowledge_base("innovation grant", db_path=test_db_path)
    assert len(search_pending) == 0

    # 3. Student tries to publish -> MUST FAIL with AuthorizationError
    with pytest.raises(AuthorizationError):
        publish_document(doc["id"], student1_user, db_path=test_db_path)

    # 4. Admin publishes document
    publish_ok = publish_document(doc["id"], admin_user, review_notes="Approved by Registrar", db_path=test_db_path)
    assert publish_ok is True

    # Check status updated
    updated = get_document_by_id(doc["id"], db_path=test_db_path)
    assert updated["status"] == "PUBLISHED"

    # CRITICAL CHECK: Once published, RAG search MUST return grounded results!
    search_published = search_published_knowledge_base("innovation grant", db_path=test_db_path)
    assert len(search_published) >= 1
    assert search_published[0]["document_title"] == "Special Research Grant Policy"
    assert search_published[0]["verified_official"] is True

    # 5. Unpublish document -> search should no longer return it
    unpublish_document(doc["id"], admin_user, reason="Archived policy", db_path=test_db_path)
    search_after_unpublish = search_published_knowledge_base("innovation grant", db_path=test_db_path)
    assert len(search_after_unpublish) == 0


def test_document_replacement_and_versioning(test_db_path, admin_user):
    pdf_v1 = generate_pdf_doc(
        "Canteen_Rules_v1.pdf",
        "Cafeteria Operations Code",
        [("Section 1", "Cafeteria open 9am to 6pm.")]
    )
    doc_v1 = add_document(
        file_path=pdf_v1,
        original_filename="Canteen_Rules_v1.pdf",
        title="Cafeteria Operations Code",
        uploaded_by_user_id=admin_user["id"],
        uploaded_by_username=admin_user["username"],
        run_ai_analysis=False,
        db_path=test_db_path
    )
    publish_document(doc_v1["id"], admin_user, db_path=test_db_path)

    # Replace with v2
    pdf_v2 = generate_pdf_doc(
        "Canteen_Rules_v2.pdf",
        "Cafeteria Operations Code",
        [("Section 1", "Cafeteria open 8am to 8pm.")]
    )
    doc_v2 = replace_document(
        old_doc_id=doc_v1["id"],
        new_file_path=pdf_v2,
        new_original_filename="Canteen_Rules_v2.pdf",
        admin_user=admin_user,
        db_path=test_db_path
    )

    # Old doc must be REPLACED
    old_doc_record = get_document_by_id(doc_v1["id"], db_path=test_db_path)
    assert old_doc_record["status"] == "REPLACED"

    # New doc must have version = 2 and start in PENDING_REVIEW
    assert doc_v2["version"] == 2
    assert doc_v2["status"] == "PENDING_REVIEW"
    assert doc_v2["previous_version_id"] == doc_v1["id"]
