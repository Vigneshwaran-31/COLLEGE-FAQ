"""
CrewAI Workflow Orchestrator for DUM DUM Group of Institution.
Coordinates multi-agent question answering, grounded verification, quota resilience,
and AI document drafting with persistence to the SQLite inquiry history.
"""
import json
import re
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from crewai import Crew, Process

from config import PRIMARY_MODEL, FALLBACK_MODELS, COLLEGE_NAME
from agents import (
    create_question_analysis_agent,
    create_retrieval_agent,
    create_answer_verification_agent,
    create_document_drafting_agent,
    get_gemini_llm,
    set_active_model,
    get_active_model_name
)
from tasks import (
    create_analysis_task,
    create_retrieval_task,
    create_verification_and_answer_task,
    create_document_draft_task
)
from knowledge_base import search_published_knowledge_base
from database import get_db_connection
from audit_service import log_event
from document_service import build_standard_draft


class PipelineError(Exception):
    """Raised when pipeline encounters an unrecoverable error."""
    pass


def extract_category_from_text(text: str) -> str:
    """Extracts institutional domain category from text."""
    lower = text.lower()
    categories = [
        ("Attendance", ["attendance", "leave", "absence", "condonation", "75%"]),
        ("Examinations", ["exam", "examination", "mid-term", "end-sem", "admit card", "grade", "results"]),
        ("Fees & Scholarships", ["fee", "tuition", "fine", "scholarship", "dues", "payment"]),
        ("Library", ["library", "books", "borrow", "reading room", "return"]),
        ("Bonafide & Certificates", ["bonafide", "certificate", "character", "transcript"]),
        ("Hostel Facilities", ["hostel", "mess", "curfew", "warden", "room"]),
        ("Courses & Departments", ["department", "course", "syllabus", "b.tech", "mca", "diploma"]),
        ("Office Timings", ["office hours", "timings", "registrar office", "working hours"])
    ]
    for cat, kws in categories:
        if any(kw in lower for kw in kws):
            return cat
    return "General Institutional Inquiry"


def run_faq_pipeline(
    question: str,
    student_user: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Executes the multi-agent College FAQ pipeline:
    1. Search published official knowledge base for grounded excerpts.
    2. If no official documents found, sets UNVERIFIED status immediately.
    3. If official documents exist, runs Question Analysis, Retrieval, and Verification agents.
    4. Handles Gemini API errors (429 quota exhaustion, 404 model deprecation) cleanly.
    5. Saves question and grounded response to student inquiry history.
    """
    clean_question = question.strip()
    if not clean_question:
        return {
            "answer": "Please ask a question regarding DUM DUM Group of Institution rules, schedules, or policies.",
            "verification_status": "UNVERIFIED",
            "sources": [],
            "category": "General Institutional Inquiry"
        }

    # 1. Deterministic Knowledge Base Search on PUBLISHED documents only
    retrieved_sources = search_published_knowledge_base(clean_question, top_k=4, db_path=db_path)
    has_published_sources = len(retrieved_sources) > 0
    inferred_category = extract_category_from_text(clean_question)

    # 2. If NO published documents found in the database, return honest unverified response
    if not has_published_sources:
        unverified_answer = (
            f"### Official Inquiry Response\n\n"
            f"**Verification Status:** ⚠️ **UNVERIFIED BY OFFICIAL RECORDS**\n\n"
            f"According to the official and published records of **{COLLEGE_NAME}**, "
            f"no verified policy document or circular was found regarding your question:\n"
            f"> *\"{clean_question}\"*\n\n"
            f"**Important Institutional Note:**\n"
            f"- Our AI assistant is strictly prohibited from inventing college rules, dates, or regulations.\n"
            f"- For authoritative guidance on this matter, please visit the Administrative Office during official working hours or consult your Department Head.\n\n"
            f"**Source Citation:** None (No verified published document matched this inquiry)."
        )

        # Record inquiry in DB if student is authenticated
        if student_user:
            record_student_inquiry(
                student_id=student_user["id"],
                question=clean_question,
                category=inferred_category,
                answer=unverified_answer,
                verification_status="UNVERIFIED",
                sources=[],
                db_path=db_path
            )

        return {
            "answer": unverified_answer,
            "verification_status": "UNVERIFIED",
            "sources": [],
            "category": inferred_category,
            "raw_crew_output": "No published sources found."
        }

    # 3. We have verified sources! Run CrewAI Multi-Agent Pipeline
    answer_text = ""
    verification_status = "VERIFIED_OFFICIAL"
    crew_output_str = ""

    # Attempt execution with model fallback
    models_to_try = [get_active_model_name()] + [m for m in FALLBACK_MODELS if m != get_active_model_name()]
    execution_success = False

    for model_candidate in models_to_try:
        try:
            llm = get_gemini_llm(force_model=model_candidate)
            analysis_agent = create_question_analysis_agent(llm)
            retrieval_agent = create_retrieval_agent(llm)
            verification_agent = create_answer_verification_agent(llm)

            task1 = create_analysis_task(analysis_agent, clean_question)
            task2 = create_retrieval_task(retrieval_agent, clean_question, context_tasks=[task1])
            task3 = create_verification_and_answer_task(verification_agent, clean_question, context_tasks=[task1, task2])

            crew = Crew(
                agents=[analysis_agent, retrieval_agent, verification_agent],
                tasks=[task1, task2, task3],
                process=Process.sequential,
                verbose=False
            )

            result = crew.kickoff()
            crew_output_str = result.raw if hasattr(result, "raw") else str(result)
            answer_text = crew_output_str
            set_active_model(model_candidate)
            execution_success = True
            break
        except Exception as e:
            err_msg = str(e)
            # Check for Quota / Rate limit (429)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                log_event(
                    action="GEMINI_QUOTA_EXHAUSTED",
                    actor_username=student_user.get("username", "Student") if student_user else "Guest",
                    actor_role="student" if student_user else "guest",
                    details=f"Model {model_candidate} reached quota limit. Error: {err_msg[:120]}",
                    severity="WARNING",
                    db_path=db_path
                )
                continue
            # Check for Deprecated model (404)
            elif "404" in err_msg or "NOT_FOUND" in err_msg:
                continue
            else:
                # Other error, try fallback model
                continue

    # If CrewAI execution failed due to quota or network, synthesize directly from grounded retrieved chunks
    if not execution_success:
        answer_text, verification_status = synthesize_grounded_answer_from_chunks(
            clean_question, retrieved_sources
        )

    # Clean up sources list for presentation
    formatted_sources = [
        {
            "document_title": s["document_title"],
            "page_number": s["page_number"],
            "filename": s["original_filename"],
            "snippet": s["content"][:200] + ("..." if len(s["content"]) > 200 else "")
        }
        for s in retrieved_sources
    ]

    # Record inquiry in DB
    if student_user:
        record_student_inquiry(
            student_id=student_user["id"],
            question=clean_question,
            category=inferred_category,
            answer=answer_text,
            verification_status=verification_status,
            sources=formatted_sources,
            db_path=db_path
        )

    return {
        "answer": answer_text,
        "verification_status": verification_status,
        "sources": formatted_sources,
        "category": inferred_category,
        "raw_crew_output": crew_output_str
    }


def synthesize_grounded_answer_from_chunks(
    question: str,
    chunks: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    Fallback grounded response synthesizer when LLM quota is momentarily reached.
    Synthesizes answer strictly from verified published database excerpts.
    """
    doc_titles = list(set(c["document_title"] for c in chunks))
    page_refs = [f"{c['document_title']} (Page {c['page_number']})" for c in chunks]

    body_parts = [
        f"### Official Policy Response (Direct Grounded Excerpts)\n",
        f"**Verification Status:** ✅ **VERIFIED OFFICIAL SOURCE**\n\n",
        f"Based on ratified institutional documents published by **{COLLEGE_NAME}**, "
        f"here are the relevant official provisions regarding your query:\n\n"
    ]

    for idx, c in enumerate(chunks, 1):
        body_parts.append(
            f"**Provision {idx}** *(Source: {c['document_title']}, Page {c['page_number']})*:\n"
            f"> {c['content']}\n\n"
        )

    body_parts.append(
        f"**Verified Sources:**\n" + "\n".join([f"- {ref}" for ref in page_refs])
    )

    return "".join(body_parts), "VERIFIED_OFFICIAL"


def record_student_inquiry(
    student_id: int,
    question: str,
    category: str,
    answer: str,
    verification_status: str,
    sources: List[Dict[str, Any]],
    db_path: Optional[Path] = None
):
    """Stores student FAQ inquiry and grounded answer into the database."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO faq_inquiries (student_id, question, category, answer, verification_status, sources_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            question,
            category,
            answer,
            verification_status,
            json.dumps(sources)
        ))

        log_event(
            action="FAQ_INQUIRY_PROCESSED",
            actor_id=student_id,
            actor_role="student",
            target_entity="faq_inquiries",
            target_id=str(cursor.lastrowid),
            details=f"Inquiry processed with status {verification_status} ({len(sources)} sources)",
            severity="INFO",
            db_path=db_path,
            conn=conn
        )


def run_document_drafting_pipeline(
    request_data: Dict[str, Any]
) -> str:
    """
    Executes Document Request Drafting Agent to prepare standardized institutional certificate draft.
    Falls back gracefully to approved template if Gemini API limit is met.
    """
    models_to_try = [get_active_model_name()] + [m for m in FALLBACK_MODELS if m != get_active_model_name()]

    for model_candidate in models_to_try:
        try:
            llm = get_gemini_llm(force_model=model_candidate)
            drafter = create_document_drafting_agent(llm)
            draft_task = create_document_draft_task(drafter, request_data)

            crew = Crew(
                agents=[drafter],
                tasks=[draft_task],
                process=Process.sequential,
                verbose=False
            )
            result = crew.kickoff()
            raw_text = result.raw if hasattr(result, "raw") else str(result)
            if raw_text and len(raw_text.strip()) > 30:
                set_active_model(model_candidate)
                return raw_text.strip()
        except Exception:
            continue

    # Fallback to standard institutional template
    return build_standard_draft(
        doc_type=request_data.get("doc_type", "BONAFIDE"),
        student_name=request_data.get("student_name", "Student"),
        roll_number=request_data.get("roll_number", "N/A"),
        department=request_data.get("department", "Academics"),
        year_semester=request_data.get("year_semester", "Current"),
        purpose=request_data.get("purpose", "Official requirement"),
        supporting_notes=request_data.get("supporting_notes")
    )


def get_student_inquiry_history(
    student_id: int,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Retrieves all inquiries submitted by a specific authenticated student."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM faq_inquiries
            WHERE student_id = ?
            ORDER BY id DESC
        """, (student_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["sources"] = json.loads(d["sources_json"]) if d["sources_json"] else []
            except Exception:
                d["sources"] = []
            result.append(d)
        return result
