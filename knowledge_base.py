"""
Knowledge Base Management and RAG Retrieval Engine for DUM DUM Group of Institution.
Enforces admin review gates before publishing official sources, document versioning,
and strictly retrieves ONLY from verified, published institutional documents.
"""
import json
import math
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from database import get_db_connection
from document_processor import (
    extract_document_content,
    chunk_document_pages,
    analyze_document_with_gemini,
    save_uploaded_file,
    validate_file
)
from auth_service import require_admin
from audit_service import log_event


class KnowledgeBaseError(Exception):
    """Raised when knowledge base operations encounter an error."""
    pass


def add_document(
    file_path: Path,
    original_filename: str,
    title: str,
    uploaded_by_user_id: int,
    uploaded_by_username: str,
    run_ai_analysis: bool = True,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Ingests a new document into the Knowledge Base in PENDING_REVIEW status.
    Extracts text/OCR, creates semantic chunks, and executes Gemini analysis.
    Only authorized administrators can publish the document for student retrieval.
    """
    if not file_path.exists():
        raise KnowledgeBaseError(f"File not found at path: {file_path}")

    file_size = file_path.stat().st_size
    file_type = file_path.suffix.lower()

    # Extract text from PDF / image
    pages_data = extract_document_content(file_path)
    page_count = len(pages_data)
    full_text = "\n\n".join([p["text"] for p in pages_data])

    # Generate semantic chunks
    chunks = chunk_document_pages(pages_data)

    # Perform Gemini or heuristic analysis
    analysis = {}
    if run_ai_analysis:
        analysis = analyze_document_with_gemini(full_text, title)
    else:
        analysis = {
            "summary": f"Uploaded document: {title}",
            "topics": ["General"],
            "extracted_rules": [],
            "important_dates": [],
            "relevant_sections": []
        }

    topics_json = json.dumps(analysis.get("topics", []))
    rules_json = json.dumps(analysis.get("extracted_rules", []))
    dates_json = json.dumps(analysis.get("important_dates", []))
    summary_text = analysis.get("summary", "")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (
                title, filename, original_filename, file_type, file_size, file_path,
                uploaded_by, status, version, page_count, summary, topics, extracted_rules,
                important_dates
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_REVIEW', 1, ?, ?, ?, ?, ?)
        """, (
            title,
            file_path.name,
            original_filename,
            file_type,
            file_size,
            str(file_path),
            uploaded_by_user_id,
            page_count,
            summary_text,
            topics_json,
            rules_json,
            dates_json
        ))
        doc_id = cursor.lastrowid

        # Insert chunks
        chunk_records = [
            (doc_id, ch["chunk_index"], ch["page_number"], ch.get("heading"), ch["content"], ch.get("token_count", 0))
            for ch in chunks
        ]
        cursor.executemany("""
            INSERT INTO document_chunks (document_id, chunk_index, page_number, heading, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, chunk_records)

        log_event(
            action="DOCUMENT_UPLOADED",
            actor_id=uploaded_by_user_id,
            actor_username=uploaded_by_username,
            actor_role="admin",
            target_entity="documents",
            target_id=str(doc_id),
            details=f"Uploaded '{title}' ({original_filename}, {page_count} pages). Status: PENDING_REVIEW",
            severity="INFO",
            db_path=db_path,
            conn=conn
        )

        cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        return dict(cursor.fetchone())


def publish_document(
    document_id: int,
    admin_user: Dict[str, Any],
    review_notes: str = "",
    db_path: Optional[Path] = None,
) -> bool:
    """
    Publishes a verified document as an official knowledge source.
    Requires administrator role.
    """
    require_admin(admin_user)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        doc = cursor.fetchone()
        if not doc:
            raise KnowledgeBaseError(f"Document with ID {document_id} not found.")

        cursor.execute("""
            UPDATE documents
            SET status = 'PUBLISHED',
                verified_by = ?,
                verified_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (admin_user["id"], document_id))

        log_event(
            action="DOCUMENT_PUBLISHED",
            actor_id=admin_user["id"],
            actor_username=admin_user["username"],
            actor_role="admin",
            target_entity="documents",
            target_id=str(document_id),
            details=f"Admin published official document '{doc['title']}'. Notes: {review_notes}",
            severity="AUDIT",
            db_path=db_path,
            conn=conn
        )
        return True


def unpublish_document(
    document_id: int,
    admin_user: Dict[str, Any],
    reason: str = "",
    db_path: Optional[Path] = None,
) -> bool:
    """
    Unpublishes a document, immediately removing it from active student FAQ retrieval.
    Requires administrator role.
    """
    require_admin(admin_user)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        doc = cursor.fetchone()
        if not doc:
            raise KnowledgeBaseError(f"Document with ID {document_id} not found.")

        cursor.execute("""
            UPDATE documents
            SET status = 'UNPUBLISHED'
            WHERE id = ?
        """, (document_id,))

        log_event(
            action="DOCUMENT_UNPUBLISHED",
            actor_id=admin_user["id"],
            actor_username=admin_user["username"],
            actor_role="admin",
            target_entity="documents",
            target_id=str(document_id),
            details=f"Admin unpublished document '{doc['title']}'. Reason: {reason}",
            severity="WARNING",
            db_path=db_path,
            conn=conn
        )
        return True


def replace_document(
    old_doc_id: int,
    new_file_path: Path,
    new_original_filename: str,
    admin_user: Dict[str, Any],
    new_title: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Replaces an existing document with a revised version.
    Old document is marked as 'REPLACED'. The new document is created with version + 1
    and starts in PENDING_REVIEW until explicitly approved.
    """
    require_admin(admin_user)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (old_doc_id,))
        old_doc = cursor.fetchone()
        if not old_doc:
            raise KnowledgeBaseError(f"Original document with ID {old_doc_id} not found.")

        # Mark old document as REPLACED
        cursor.execute("UPDATE documents SET status = 'REPLACED' WHERE id = ?", (old_doc_id,))

        title = new_title or old_doc["title"]
        new_version = old_doc["version"] + 1

    # Ingest new document
    new_doc = add_document(
        file_path=new_file_path,
        original_filename=new_original_filename,
        title=title,
        uploaded_by_user_id=admin_user["id"],
        uploaded_by_username=admin_user["username"],
        run_ai_analysis=True,
        db_path=db_path
    )

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE documents
            SET version = ?, previous_version_id = ?
            WHERE id = ?
        """, (new_version, old_doc_id, new_doc["id"]))

        log_event(
            action="DOCUMENT_REPLACED",
            actor_id=admin_user["id"],
            actor_username=admin_user["username"],
            actor_role="admin",
            target_entity="documents",
            target_id=str(new_doc["id"]),
            details=f"Replaced doc ID {old_doc_id} with new version {new_version} (Doc ID {new_doc['id']})",
            severity="AUDIT",
            db_path=db_path,
            conn=conn
        )

        cursor.execute("SELECT * FROM documents WHERE id = ?", (new_doc["id"],))
        return dict(cursor.fetchone())


def reindex_document(
    document_id: int,
    admin_user: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Re-extracts text, regenerates chunks, and re-runs Gemini analysis for a document.
    """
    require_admin(admin_user)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        doc = cursor.fetchone()
        if not doc:
            raise KnowledgeBaseError(f"Document with ID {document_id} not found.")

        file_path = Path(doc["file_path"])
        if not file_path.exists():
            raise KnowledgeBaseError(f"Underlying file missing on disk: {file_path}")

        # Delete existing chunks
        cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))

    # Re-extract
    pages_data = extract_document_content(file_path)
    full_text = "\n\n".join([p["text"] for p in pages_data])
    chunks = chunk_document_pages(pages_data)
    analysis = analyze_document_with_gemini(full_text, doc["title"])

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        # Insert fresh chunks
        chunk_records = [
            (document_id, ch["chunk_index"], ch["page_number"], ch.get("heading"), ch["content"], ch.get("token_count", 0))
            for ch in chunks
        ]
        cursor.executemany("""
            INSERT INTO document_chunks (document_id, chunk_index, page_number, heading, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, chunk_records)

        # Update metadata
        cursor.execute("""
            UPDATE documents
            SET summary = ?, topics = ?, extracted_rules = ?, important_dates = ?, page_count = ?
            WHERE id = ?
        """, (
            analysis.get("summary", ""),
            json.dumps(analysis.get("topics", [])),
            json.dumps(analysis.get("extracted_rules", [])),
            json.dumps(analysis.get("important_dates", [])),
            len(pages_data),
            document_id
        ))

        log_event(
            action="DOCUMENT_REINDEXED",
            actor_id=admin_user["id"],
            actor_username=admin_user["username"],
            actor_role="admin",
            target_entity="documents",
            target_id=str(document_id),
            details=f"Reindexed document '{doc['title']}'. Created {len(chunks)} chunks.",
            severity="INFO",
            db_path=db_path,
            conn=conn
        )

        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        return dict(cursor.fetchone())


def get_all_documents(
    filter_status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieves all documents, optionally filtered by status."""
    query = "SELECT * FROM documents"
    params = []
    if filter_status and filter_status != "ALL":
        query += " WHERE status = ?"
        params.append(filter_status)
    query += " ORDER BY id DESC"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["topics_list"] = json.loads(d["topics"]) if d["topics"] else []
            except Exception:
                d["topics_list"] = []
            try:
                d["rules_list"] = json.loads(d["extracted_rules"]) if d["extracted_rules"] else []
            except Exception:
                d["rules_list"] = []
            try:
                d["dates_list"] = json.loads(d["important_dates"]) if d["important_dates"] else []
            except Exception:
                d["dates_list"] = []
            result.append(d)
        return result


def get_document_by_id(document_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves document by ID with parsed JSON metadata."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ["topics", "extracted_rules", "important_dates"]:
            try:
                d[f"{key}_parsed"] = json.loads(d[key]) if d[key] else []
            except Exception:
                d[f"{key}_parsed"] = []
        return d


def get_document_chunks(document_id: int, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieves all text chunks for a document."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM document_chunks
            WHERE document_id = ?
            ORDER BY chunk_index ASC
        """, (document_id,))
        return [dict(r) for r in cursor.fetchall()]


def search_published_knowledge_base(
    query: str,
    top_k: int = 4,
    min_score_threshold: float = 0.12,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    RAG Retrieval Engine:
    Searches ONLY documents where status = 'PUBLISHED'.
    Uses hybrid scoring (term frequency, exact phrase bonus, keyword overlap) against official chunks.
    Returns ranked chunks with verified source citations.
    """
    clean_query = query.strip().lower()
    if not clean_query:
        return []

    query_tokens = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', clean_query))
    # Filter common stopwords
    stopwords = {"what", "when", "where", "which", "who", "whom", "this", "that", "there", "their", "have", "from", "with", "about", "does", "will", "tell", "give", "info", "college", "group", "institution", "dumdum"}
    meaningful_tokens = [t for t in query_tokens if t not in stopwords]
    if not meaningful_tokens:
        meaningful_tokens = list(query_tokens)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        # Query only chunks from PUBLISHED documents
        cursor.execute("""
            SELECT 
                dc.id AS chunk_id,
                dc.document_id,
                dc.chunk_index,
                dc.page_number,
                dc.heading,
                dc.content,
                d.title AS document_title,
                d.original_filename,
                d.version,
                d.topics
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.status = 'PUBLISHED'
        """)
        rows = cursor.fetchall()

    scored_chunks = []
    for r in rows:
        content_lower = r["content"].lower()
        heading_lower = (r["heading"] or "").lower()
        title_lower = r["document_title"].lower()

        # 1. Token matches
        matched_tokens = sum(1 for token in meaningful_tokens if token in content_lower)
        heading_matches = sum(1 for token in meaningful_tokens if token in heading_lower or token in title_lower)

        token_score = matched_tokens / max(len(meaningful_tokens), 1)

        # 2. Phrase match bonus
        phrase_bonus = 0.4 if clean_query in content_lower else 0.0

        # 3. Heading bonus
        heading_bonus = 0.25 if heading_matches > 0 else 0.0

        total_score = (token_score * 0.6) + phrase_bonus + heading_bonus

        if total_score >= min_score_threshold:
            scored_chunks.append({
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "document_title": r["document_title"],
                "original_filename": r["original_filename"],
                "page_number": r["page_number"],
                "heading": r["heading"] or f"Page {r['page_number']}",
                "content": r["content"],
                "relevance_score": round(total_score, 4),
                "verified_official": True
            })

    # Sort descending by score
    scored_chunks.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored_chunks[:top_k]
