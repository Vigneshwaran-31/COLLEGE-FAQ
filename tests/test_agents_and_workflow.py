"""
Tests for CrewAI Multi-Agent FAQ workflow, grounded answering, citation tracking,
unknown question handling, and Gemini quota error resilience.
"""
import pytest
from unittest.mock import patch, MagicMock
from knowledge_base import add_document, publish_document
from seed_sample_documents import generate_pdf_doc
from workflow import (
    run_faq_pipeline,
    get_student_inquiry_history,
    extract_category_from_text,
    synthesize_grounded_answer_from_chunks
)


@pytest.fixture
def seeded_kb_db(test_db_path, admin_user):
    """Seeds official attendance and library documents into test database."""
    p1 = generate_pdf_doc(
        "Attendance_Rules_Test.pdf",
        "Attendance and Leave Regulations 2026",
        [
            ("Section 1: Mandatory Attendance", "Students must maintain minimum 75% attendance to qualify for examinations."),
            ("Section 2: Medical Condonation", "Attendance between 65% and 74% may be condoned by the Dean upon medical certificate.")
        ]
    )
    d1 = add_document(p1, p1.name, "Attendance and Leave Regulations 2026", admin_user["id"], admin_user["username"], run_ai_analysis=False, db_path=test_db_path)
    publish_document(d1["id"], admin_user, db_path=test_db_path)

    p2 = generate_pdf_doc(
        "Library_Manual_Test.pdf",
        "Central Library Operational Regulations 2026",
        [
            ("Section 1: Working Hours", "Central Library operates Monday to Friday from 8:00 AM to 8:00 PM."),
            ("Section 2: Borrow Limits", "Undergraduate students can borrow 4 books for 14 calendar days.")
        ]
    )
    d2 = add_document(p2, p2.name, "Central Library Operational Regulations 2026", admin_user["id"], admin_user["username"], run_ai_analysis=False, db_path=test_db_path)
    publish_document(d2["id"], admin_user, db_path=test_db_path)

    return test_db_path


def test_known_faq_question_grounded_answer(seeded_kb_db, student1_user):
    # Mock external service only in automated test as required by test specification
    mock_response = MagicMock()
    mock_response.raw = "According to Attendance and Leave Regulations 2026 (Page 1), students must maintain a minimum of 75% attendance."
    
    with patch("crewai.Crew.kickoff", return_value=mock_response):
        result = run_faq_pipeline(
            question="What is the minimum attendance requirement?",
            student_user=student1_user,
            db_path=seeded_kb_db
        )

    # Must be verified
    assert result["verification_status"] == "VERIFIED_OFFICIAL"
    assert len(result["sources"]) >= 1
    # Check citations
    source_titles = [s["document_title"] for s in result["sources"]]
    assert any("Attendance" in t for t in source_titles)
    for s in result["sources"]:
        assert "page_number" in s
        assert s["page_number"] > 0

    # Check student history persistence
    history = get_student_inquiry_history(student1_user["id"], db_path=seeded_kb_db)
    assert len(history) == 1
    assert history[0]["verification_status"] == "VERIFIED_OFFICIAL"


def test_unknown_faq_question_unverified_answer(seeded_kb_db, student1_user):
    # Query about ungrounded topic
    unknown_query = "What is the policy on launching personal satellites from the college campus?"
    result = run_faq_pipeline(
        question=unknown_query,
        student_user=student1_user,
        db_path=seeded_kb_db
    )

    # Must be UNVERIFIED
    assert result["verification_status"] == "UNVERIFIED"
    assert len(result["sources"]) == 0
    # Must refuse to invent official college rules
    assert "could not be verified" in result["answer"].lower() or "unverified" in result["answer"].lower()

    # History record must reflect UNVERIFIED
    history = get_student_inquiry_history(student1_user["id"], db_path=seeded_kb_db)
    assert len(history) == 1
    assert history[0]["verification_status"] == "UNVERIFIED"


def test_student_inquiry_isolation(seeded_kb_db, student1_user, student2_user):
    # Student 1 asks a question (mock external crew for isolated test)
    mock_resp = MagicMock(raw="Library operates 8am to 8pm.")
    with patch("crewai.Crew.kickoff", return_value=mock_resp):
        run_faq_pipeline(
            question="What are the library timings?",
            student_user=student1_user,
            db_path=seeded_kb_db
        )

    # Student 2 history must be empty (strict data isolation)
    history_s2 = get_student_inquiry_history(student2_user["id"], db_path=seeded_kb_db)
    assert len(history_s2) == 0

    # Student 1 history must have 1
    history_s1 = get_student_inquiry_history(student1_user["id"], db_path=seeded_kb_db)
    assert len(history_s1) == 1


def test_gemini_api_quota_limit_safety(seeded_kb_db, student1_user):
    """
    Verifies that when Gemini API returns 429 RESOURCE_EXHAUSTED / quota limit error,
    the system safely falls back to grounded chunk synthesis without hanging or crashing.
    """
    with patch("crewai.Crew.kickoff") as mock_kickoff:
        # Simulate Google Gemini 429 Quota Exceeded exception
        mock_kickoff.side_effect = Exception("429 RESOURCE_EXHAUSTED: You exceeded your current quota for gemini-2.5-flash.")

        result = run_faq_pipeline(
            question="What is the library operational schedule?",
            student_user=student1_user,
            db_path=seeded_kb_db
        )

        # Must NOT crash, must synthesize from retrieved verified chunks!
        assert result is not None
        assert result["verification_status"] == "VERIFIED_OFFICIAL"
        assert len(result["sources"]) >= 1
        assert "Official Policy Response" in result["answer"] or "Library" in result["answer"]
