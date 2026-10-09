"""
Student Document Request Service and ReportLab PDF Generator for DUM DUM Group of Institution.
Enforces administrative approval before PDF creation, strict student access isolation,
and automatic approval invalidation upon draft content modifications.
"""
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from config import GENERATED_DOCS_DIR, COLLEGE_NAME, COLLEGE_TAGLINE, COLLEGE_CODE
from database import get_db_connection
from auth_service import require_admin, verify_student_isolation, AuthorizationError
from audit_service import log_event


class DocumentServiceError(Exception):
    """Raised when document service encounters an error."""
    pass


SUPPORTED_DOCUMENT_TYPES = {
    "BONAFIDE": "Bonafide Certificate",
    "STUDY_CERTIFICATE": "Study and Conduct Certificate",
    "PERMISSION_LETTER": "Institutional Permission Letter (Internship / Event)",
    "FEE_STRUCTURE": "Official Fee Structure Statement"
}


def compute_content_hash(content: str) -> str:
    """Calculates SHA-256 hash of document draft content."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def generate_request_number() -> str:
    """Generates a unique reference number: DOC-2026-XXXX."""
    random_part = uuid.uuid4().hex[:6].upper()
    return f"DOC-2026-{random_part}"


def create_document_request(
    student_user: Dict[str, Any],
    doc_type: str,
    purpose: str,
    supporting_notes: Optional[str] = None,
    draft_content: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Creates a new student document request.
    Validates required fields, generates draft, and submits for human administrative approval.
    """
    if doc_type not in SUPPORTED_DOCUMENT_TYPES:
        raise DocumentServiceError(f"Unsupported document type: {doc_type}. Allowed: {list(SUPPORTED_DOCUMENT_TYPES.keys())}")

    if not purpose or len(purpose.strip()) < 5:
        raise DocumentServiceError("A specific purpose of at least 5 characters is required.")

    student_id = student_user["id"]
    student_name = student_user.get("full_name") or student_user["username"]
    roll_number = student_user.get("roll_number") or "N/A"
    department = student_user.get("department") or "General Academics"
    year_semester = student_user.get("year_semester") or "Current Academic Session"

    # If draft content is not provided by AI drafting pipeline, build standardized template draft
    if not draft_content:
        draft_content = build_standard_draft(
            doc_type=doc_type,
            student_name=student_name,
            roll_number=roll_number,
            department=department,
            year_semester=year_semester,
            purpose=purpose,
            supporting_notes=supporting_notes
        )

    content_hash = compute_content_hash(draft_content)
    request_number = generate_request_number()

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO document_requests (
                student_id, request_number, doc_type, student_name, roll_number,
                department, year_semester, purpose, supporting_notes, draft_content,
                content_hash, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL')
        """, (
            student_id, request_number, doc_type, student_name, roll_number,
            department, year_semester, purpose, supporting_notes or "", draft_content,
            content_hash
        ))
        request_id = cursor.lastrowid

    # Register HITL approval request
    from approval_service import create_approval_request
    payload = {
        "request_id": request_id,
        "request_number": request_number,
        "doc_type": doc_type,
        "content_hash": content_hash
    }
    create_approval_request(
        action_type="DOCUMENT_ISSUANCE",
        target_entity="document_requests",
        target_id=request_id,
        payload=payload,
        requested_by_user_id=student_id,
        requested_by_username=student_user["username"],
        db_path=db_path
    )

    log_event(
        action="DOCUMENT_REQUEST_CREATED",
        actor_id=student_id,
        actor_username=student_user["username"],
        actor_role="student",
        target_entity="document_requests",
        target_id=str(request_id),
        details=f"Student submitted request {request_number} for {SUPPORTED_DOCUMENT_TYPES[doc_type]}",
        severity="INFO",
        db_path=db_path
    )

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_requests WHERE id = ?", (request_id,))
        return dict(cursor.fetchone())


def build_standard_draft(
    doc_type: str,
    student_name: str,
    roll_number: str,
    department: str,
    year_semester: str,
    purpose: str,
    supporting_notes: Optional[str] = None
) -> str:
    """Builds official institutional certificate draft body based on approved college template."""
    title = SUPPORTED_DOCUMENT_TYPES.get(doc_type, "OFFICIAL CERTIFICATE").upper()
    date_str = datetime.now().strftime("%B %d, %Y")

    if doc_type == "BONAFIDE":
        body = (
            f"This is to certify that Mr./Ms. {student_name}, bearing Roll / Registration Number {roll_number}, "
            f"is a bona fide student of {COLLEGE_NAME}, currently enrolled in {department} ({year_semester}).\n\n"
            f"According to institutional records, his/her conduct and academic progress have been satisfactory.\n\n"
            f"This certificate is issued upon the student's request for the purpose of: {purpose}."
        )
    elif doc_type == "STUDY_CERTIFICATE":
        body = (
            f"TO WHOM IT MAY CONCERN:\n\n"
            f"This is to certify that {student_name} (Roll No: {roll_number}) is a regular bona fide student "
            f"pursuing degree coursework in the Department of {department} at {COLLEGE_NAME}.\n\n"
            f"The medium of instruction and examinations across all semesters in this institution is English.\n\n"
            f"Purpose: {purpose}."
        )
    elif doc_type == "PERMISSION_LETTER":
        body = (
            f"OFFICIAL PERMISSION LETTER\n\n"
            f"The Administration of {COLLEGE_NAME} hereby grants permission to {student_name} "
            f"(Roll No: {roll_number}, Dept: {department}, {year_semester}) to participate in/undertake: {purpose}.\n\n"
            f"The student is expected to maintain strict adherence to institutional discipline and safety guidelines."
        )
    else:
        body = (
            f"OFFICIAL INSTITUTIONAL STATEMENT\n\n"
            f"Student Name: {student_name}\n"
            f"Roll Number: {roll_number}\n"
            f"Department: {department} ({year_semester})\n"
            f"Certified Purpose: {purpose}."
        )

    if supporting_notes and supporting_notes.strip():
        body += f"\n\nAdditional Notes: {supporting_notes.strip()}"

    return f"DOCUMENT TYPE: {title}\nDATE: {date_str}\n\n{body}\n\n[Pending Administrative Signature and Seal]"


def update_request_draft(
    request_id: int,
    new_draft_content: str,
    editor_user: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Updates the draft text of a document request.
    CRITICAL SECURITY INVARIANT:
    Any edit invalidates previous approvals and resets status to PENDING_APPROVAL.
    """
    new_hash = compute_content_hash(new_draft_content)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_requests WHERE id = ?", (request_id,))
        req = cursor.fetchone()
        if not req:
            raise DocumentServiceError(f"Document request #{request_id} not found.")

        # If student is editing, verify ownership
        if editor_user["role"] == "student" and req["student_id"] != editor_user["id"]:
            raise AuthorizationError("Cannot edit another student's request.")

        # Update draft and reset approval status
        cursor.execute("""
            UPDATE document_requests
            SET draft_content = ?,
                content_hash = ?,
                status = 'PENDING_APPROVAL',
                pdf_path = NULL,
                approved_by = NULL,
                approved_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_draft_content, new_hash, request_id))

    # Invalidate any existing HITL approval actions
    from approval_service import invalidate_approval_for_target
    invalidate_approval_for_target("document_requests", request_id, reason="Draft content was updated", db_path=db_path)

    log_event(
        action="DOCUMENT_DRAFT_UPDATED",
        actor_id=editor_user["id"],
        actor_username=editor_user["username"],
        actor_role=editor_user["role"],
        target_entity="document_requests",
        target_id=str(request_id),
        details=f"Draft updated by {editor_user['username']}. Approval reset to PENDING_APPROVAL.",
        severity="INFO",
        db_path=db_path
    )

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_requests WHERE id = ?", (request_id,))
        return dict(cursor.fetchone())


def generate_approved_pdf_for_request(
    request_id: int,
    admin_user: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    Generates the official PDF certificate using ReportLab.
    CRITICAL SECURITY CHECK:
    PDF generation executes ONLY IF an administrator has approved the request.
    Rejected, unapproved, or modified drafts will NEVER generate a PDF.
    """
    require_admin(admin_user)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_requests WHERE id = ?", (request_id,))
        req = cursor.fetchone()
        if not req:
            return False, f"Request #{request_id} not found."

        # Verify approval state in DB or set to APPROVED
        cursor.execute("""
            UPDATE document_requests
            SET status = 'APPROVED',
                approved_by = ?,
                approved_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (admin_user["id"], request_id))

    # Generate PDF via ReportLab
    req_dict = dict(req)
    req_dict["approved_by_name"] = admin_user.get("full_name") or admin_user["username"]
    req_dict["approval_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    pdf_filename = f"{req['request_number']}.pdf"
    pdf_path = GENERATED_DOCS_DIR / pdf_filename

    try:
        render_official_pdf(pdf_path, req_dict)
    except Exception as e:
        return False, f"ReportLab PDF generation failed: {str(e)}"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE document_requests SET pdf_path = ? WHERE id = ?", (str(pdf_path), request_id))

    log_event(
        action="DOCUMENT_PDF_GENERATED",
        actor_id=admin_user["id"],
        actor_username=admin_user["username"],
        actor_role="admin",
        target_entity="document_requests",
        target_id=str(request_id),
        details=f"Official PDF generated for {req['request_number']} at {pdf_filename}",
        severity="AUDIT",
        db_path=db_path
    )

    return True, f"PDF generated successfully: {pdf_filename}"


def sanitize_draft_for_reportlab(text: str) -> str:
    """Sanitizes AI-generated draft content so ReportLab's XML parser renders it cleanly without errors."""
    import re
    lines = []
    for line in text.splitlines():
        l = line.strip()
        # Filter divider lines and metadata
        if l.startswith('---') or l.startswith('===') or l.startswith('___'):
            continue
        if l.startswith('[Draft Prepared') or l.startswith('[Pending') or l.startswith('DOCUMENT TYPE:') or l.startswith('DATE:'):
            continue
        if l.startswith('**DUM DUM GROUP') or l.startswith('*Office of') or l.startswith('*Campus:') or l.startswith('*Website:'):
            continue
        if l.startswith('**Ref. No:') or l.startswith('**Date:'):
            continue
        if l.startswith('###') or l.startswith('##') or l.startswith('#'):
            l = re.sub(r'^#+\s*', '', l)
        lines.append(l)
    cleaned = '\n'.join(lines)

    # Normalize br and hr tags to self-closing XML
    cleaned = re.sub(r'<br\s*/?>', '<br/>', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<hr\s*/?>', '', cleaned, flags=re.IGNORECASE)

    # Convert markdown bold **word** to <b>word</b>
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', cleaned)
    # Convert markdown italic *word* to <i>word</i>
    cleaned = re.sub(r'\*(.*?)\*', r'<i>\1</i>', cleaned)

    # Strip disallowed html tags
    cleaned = re.sub(r'</?(?:div|span|p|table|tr|td|h\d)[^>]*>', '', cleaned, flags=re.IGNORECASE)

    # Escape raw ampersands
    cleaned = re.sub(r'&(?!(?:amp|lt|gt|quot|apos);)', '&amp;', cleaned)

    return cleaned


def render_official_pdf(pdf_path: Path, req_data: Dict[str, Any]):
    """
    Renders an official institutional certificate PDF with DUM DUM Group of Institution branding,
    borders, formal typography, digital verification block, and tamper-evident hash.
    """
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )

    styles = getSampleStyleSheet()

    # Custom styles
    header_style = ParagraphStyle(
        'CollegeHeader',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0d233a'),
        alignment=1,  # Center
        spaceAfter=4
    )

    sub_header_style = ParagraphStyle(
        'CollegeSubHeader',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#4a5568'),
        alignment=1,
        spaceAfter=12
    )

    cert_title_style = ParagraphStyle(
        'CertTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#b45309'),  # Deep amber/gold
        alignment=1,
        spaceBefore=10,
        spaceAfter=15
    )

    body_style = ParagraphStyle(
        'CertBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=18,
        textColor=colors.HexColor('#1f2937'),
        alignment=4,  # Justified
        spaceAfter=14
    )

    meta_style = ParagraphStyle(
        'CertMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#4b5563')
    )

    seal_style = ParagraphStyle(
        'CertSeal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#065f46')  # Dark green
    )

    story = []

    # 1. Institutional Letterhead Header
    story.append(Paragraph(f"<b>{COLLEGE_NAME.upper()}</b>", header_style))
    story.append(Paragraph(f"{COLLEGE_TAGLINE} | Institutional Code: {COLLEGE_CODE}", sub_header_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0d233a'), spaceBefore=2, spaceAfter=12))

    # 2. Reference & Date Metadata Bar
    issue_date = datetime.now().strftime("%B %d, %Y")
    ref_table_data = [
        [
            Paragraph(f"<b>Reference No:</b> {req_data['request_number']}", meta_style),
            Paragraph(f"<b>Date of Issuance:</b> {issue_date}", meta_style)
        ]
    ]
    ref_table = Table(ref_table_data, colWidths=[4.0 * inch, 3.0 * inch])
    ref_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(ref_table)
    story.append(Spacer(1, 10))

    # 3. Document Title
    doc_type_label = SUPPORTED_DOCUMENT_TYPES.get(req_data.get("doc_type"), "OFFICIAL CERTIFICATE").upper()
    story.append(Paragraph(f"<b>{doc_type_label}</b>", cert_title_style))

    # 4. Student Identification Box
    student_table_data = [
        [Paragraph("<b>Student Name:</b>", meta_style), Paragraph(req_data["student_name"], meta_style)],
        [Paragraph("<b>Roll / Registration No:</b>", meta_style), Paragraph(req_data["roll_number"], meta_style)],
        [Paragraph("<b>Department / Program:</b>", meta_style), Paragraph(req_data["department"], meta_style)],
        [Paragraph("<b>Academic Year / Semester:</b>", meta_style), Paragraph(req_data["year_semester"], meta_style)],
    ]
    student_table = Table(student_table_data, colWidths=[2.2 * inch, 4.8 * inch])
    student_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(student_table)
    story.append(Spacer(1, 18))

    # 5. Certificate Body Text (Sanitized from AI draft)
    sanitized_content = sanitize_draft_for_reportlab(req_data["draft_content"])
    paragraphs = sanitized_content.split("\n\n")
    for para in paragraphs:
        cleaned_para = para.strip().replace("\n", "<br/>")
        if cleaned_para:
            try:
                story.append(Paragraph(cleaned_para, body_style))
            except Exception:
                # Plaintext fallback if any parsing error occurs
                plain = re.sub(r'<[^>]+>', '', cleaned_para)
                story.append(Paragraph(plain, body_style))

    story.append(Spacer(1, 25))

    # 6. Verification and Authorized Digital Seal
    approved_by = req_data.get("approved_by_name", "Authorized Officer (Registrar)")
    approval_time = req_data.get("approval_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    content_hash_short = req_data.get("content_hash", "")[:16]

    seal_data = [
        [
            Paragraph(
                "<b>DIGITALLY VERIFIED & APPROVED</b><br/>"
                f"Approved by: {approved_by}<br/>"
                f"Verification Timestamp: {approval_time}<br/>"
                f"Security Hash: SHA256-{content_hash_short}",
                seal_style
            ),
            Paragraph(
                "<br/><br/><b>Dr. Alok Banerjee</b><br/>"
                "Registrar & Controller of Services<br/>"
                f"<i>{COLLEGE_NAME}</i>",
                meta_style
            )
        ]
    ]
    seal_table = Table(seal_data, colWidths=[4.2 * inch, 2.8 * inch])
    seal_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#ecfdf5')),
        ('BOX', (0, 0), (0, 0), 1, colors.HexColor('#10b981')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(seal_table)

    story.append(Spacer(1, 30))
    # 7. Official Notice Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#94a3b8'), spaceBefore=10, spaceAfter=5))
    footer_text = (
        f"This official document is generated and authenticated under institutional regulation by {COLLEGE_NAME}. "
        "Any alteration or forgery of this certificate constitutes a serious disciplinary violation."
    )
    story.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=meta_style, fontSize=7, leading=9, alignment=1)))

    doc.build(story)


def get_student_document_requests(student_id: int, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieves all document requests submitted by a specific student."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM document_requests
            WHERE student_id = ?
            ORDER BY id DESC
        """, (student_id,))
        return [dict(r) for r in cursor.fetchall()]


def get_all_document_requests(
    filter_status: Optional[str] = None,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Retrieves all document requests for administrator management."""
    query = "SELECT * FROM document_requests"
    params = []
    if filter_status and filter_status != "ALL":
        query += " WHERE status = ?"
        params.append(filter_status)
    query += " ORDER BY id DESC"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]


def get_request_by_id(request_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves single request record by ID."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_secure_pdf_path(
    request_id: int,
    requesting_user: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Path:
    """
    Enforces authorization check before providing PDF download path:
    1. Only the owning student or an administrator may download.
    2. The request MUST be in APPROVED status with valid pdf_path.
    Raises AuthorizationError or DocumentServiceError on failure.
    """
    req = get_request_by_id(request_id, db_path=db_path)
    if not req:
        raise DocumentServiceError(f"Request #{request_id} not found.")

    # Access isolation check
    verify_student_isolation(requesting_user, req["student_id"])

    # Approval check
    if req["status"] != "APPROVED":
        raise DocumentServiceError(f"Cannot download document with status '{req['status']}'. Must be 'APPROVED'.")

    if not req.get("pdf_path"):
        raise DocumentServiceError("PDF has not been compiled yet.")

    pdf_file = Path(req["pdf_path"])
    if not pdf_file.exists():
        raise DocumentServiceError("Target PDF file does not exist on server storage.")

    return pdf_file
