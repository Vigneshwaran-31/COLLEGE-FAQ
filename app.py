"""
DUM DUM Group of Institution - College FAQ Agent & Administrative Approval Portal
Streamlit Application with Role-Based Student & Admin Portals, Multi-Agent FAQ Assistant,
Knowledge Base Management, and Human-in-the-Loop Approval Workflow.
"""
import streamlit as st
from pathlib import Path
import json
from datetime import datetime
import pandas as pd

from config import (
    COLLEGE_NAME,
    COLLEGE_TAGLINE,
    COLLEGE_CODE,
    GEMINI_API_KEY,
    PRIMARY_MODEL,
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_SIZE_MB,
    SMTP_ENABLED
)
from database import init_db, get_db_connection
from auth_service import (
    authenticate,
    register_student,
    get_user_by_id,
    AuthorizationError
)
from audit_service import get_audit_logs, export_audit_logs_csv, log_event
from document_processor import validate_file, save_uploaded_file
from knowledge_base import (
    add_document,
    publish_document,
    unpublish_document,
    replace_document,
    reindex_document,
    get_all_documents,
    get_document_by_id,
    get_document_chunks,
    search_published_knowledge_base
)
from approval_service import (
    get_pending_approvals,
    approve_action,
    reject_action,
    queue_email_for_approval
)
from document_service import (
    create_document_request,
    get_student_document_requests,
    get_all_document_requests,
    get_request_by_id,
    update_request_draft,
    get_secure_pdf_path,
    SUPPORTED_DOCUMENT_TYPES
)
from workflow import (
    run_faq_pipeline,
    run_document_drafting_pipeline,
    get_student_inquiry_history
)
from agents import get_active_model_name, set_active_model

# =====================================================================
# STREAMLIT PAGE CONFIG & CUSTOM STYLES
# =====================================================================

st.set_page_config(
    page_title=f"{COLLEGE_NAME} - FAQ & Approvals",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Institutional CSS
CUSTOM_CSS = """
<style>
    /* Institutional Color Palette */
    :root {
        --primary-navy: #0d233a;
        --secondary-navy: #1a365d;
        --accent-gold: #b45309;
        --accent-amber: #d97706;
        --bg-light: #f8fafc;
        --card-bg: #ffffff;
        --text-main: #1e293b;
        --border-color: #e2e8f0;
    }

    /* Main Container & Font */
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
    }

    /* College Header Banner */
    .college-header-banner {
        background: linear-gradient(135deg, #0d233a 0%, #1a365d 100%);
        color: #ffffff;
        padding: 1.6rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 12px rgba(13, 35, 58, 0.15);
        border-left: 6px solid #d97706;
    }
    .college-header-title {
        font-size: 1.85rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: 0.5px;
    }
    .college-header-tagline {
        font-size: 0.95rem;
        color: #cbd5e1;
        margin-top: 4px;
        margin-bottom: 0;
    }

    /* Card Containers */
    .custom-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }

    /* Metric Box */
    .stat-metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        border-top: 4px solid #0d233a;
    }
    .stat-metric-val {
        font-size: 1.9rem;
        font-weight: 700;
        color: #0d233a;
    }
    .stat-metric-lbl {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        color: #64748b;
        letter-spacing: 0.5px;
    }

    /* Badges */
    .badge-verified {
        display: inline-block;
        background-color: #ecfdf5;
        color: #065f46;
        border: 1px solid #10b981;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-unverified {
        display: inline-block;
        background-color: #fffbeb;
        color: #92400e;
        border: 1px solid #f59e0b;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-pending {
        display: inline-block;
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #f59e0b;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-approved {
        display: inline-block;
        background-color: #d1fae5;
        color: #065f46;
        border: 1px solid #10b981;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-rejected {
        display: inline-block;
        background-color: #fee2e2;
        color: #991b1b;
        border: 1px solid #ef4444;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Source Citation Card */
    .source-citation-card {
        background-color: #f8fafc;
        border-left: 4px solid #3b82f6;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin-top: 0.6rem;
        margin-bottom: 0.6rem;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Initialize Database
init_db()

# Initialize Session State
if "user" not in st.session_state:
    st.session_state.user = None
if "current_question" not in st.session_state:
    st.session_state.current_question = ""


# =====================================================================
# AUTHENTICATION SCREEN
# =====================================================================

def render_login_register():
    st.markdown(f"""
    <div class="college-header-banner">
        <h1 class="college-header-title">🏛️ {COLLEGE_NAME}</h1>
        <p class="college-header-tagline">{COLLEGE_TAGLINE} | Institutional Portal ({COLLEGE_CODE})</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.subheader("🔐 Secure Sign In")
        with st.form("login_form"):
            username = st.text_input("Username / Roll Number", placeholder="e.g. admin or student1")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In to Portal", use_container_width=True)

            if submit:
                user = authenticate(username, password)
                if user:
                    st.session_state.user = user
                    st.success(f"Welcome back, {user['full_name']}!")
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please verify your username and password.")

        # Quick Demo Login Buttons
        st.markdown("---")
        st.caption("⚡ **Demo Quick-Fill Credentials**:")
        demo_col1, demo_col2, demo_col3 = st.columns(3)
        with demo_col1:
            if st.button("Admin Demo", use_container_width=True):
                user = authenticate("admin", "Admin@123")
                if user:
                    st.session_state.user = user
                    st.rerun()
        with demo_col2:
            if st.button("Student 1 (Rahul)", use_container_width=True):
                user = authenticate("student1", "Student@123")
                if user:
                    st.session_state.user = user
                    st.rerun()
        with demo_col3:
            if st.button("Student 2 (Priya)", use_container_width=True):
                user = authenticate("student2", "Student@123")
                if user:
                    st.session_state.user = user
                    st.rerun()

    with col2:
        st.subheader("📝 New Student Registration")
        with st.form("register_form"):
            new_user = st.text_input("Choose Username", placeholder="e.g. rohit_cse")
            new_pass = st.text_input("Choose Password (min 6 chars)", type="password")
            full_name = st.text_input("Full Name", placeholder="e.g. Rohit Verma")
            roll_no = st.text_input("Roll / Registration No.", placeholder="e.g. DGD/2024/CSE-099")
            dept = st.selectbox("Department", [
                "Computer Science & Engineering",
                "Electronics & Communication Engineering",
                "Mechanical Engineering",
                "Civil Engineering",
                "Management Studies (MBA)",
                "Computer Applications (MCA)"
            ])
            year_sem = st.selectbox("Year & Semester", [
                "1st Year / 1st Sem", "1st Year / 2nd Sem",
                "2nd Year / 3rd Sem", "2nd Year / 4th Sem",
                "3rd Year / 5th Sem", "3rd Year / 6th Sem",
                "4th Year / 7th Sem", "4th Year / 8th Sem"
            ])
            email = st.text_input("Institutional Email", placeholder="rohit@dumdumgroup.edu")
            reg_submit = st.form_submit_button("Create Student Account", use_container_width=True)

            if reg_submit:
                ok, msg, uid = register_student(
                    new_user, new_pass, full_name, roll_no, dept, year_sem, email
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)


# =====================================================================
# SIDEBAR NAVIGATION & USER PROFILE
# =====================================================================

def render_sidebar():
    user = st.session_state.user
    st.sidebar.markdown(f"### 🏛️ {COLLEGE_NAME}")
    st.sidebar.caption(f"Institutional Code: **{COLLEGE_CODE}**")
    st.sidebar.markdown("---")

    # Profile display
    role_icon = "👨‍💼 Admin" if user["role"] == "admin" else "🎓 Student"
    st.sidebar.markdown(f"**Logged in as:** {user['full_name']}")
    st.sidebar.markdown(f"**Role:** `{role_icon}`")
    if user.get("roll_number") and user["role"] == "student":
        st.sidebar.caption(f"Roll: {user['roll_number']}")
        st.sidebar.caption(f"Dept: {user.get('department', 'N/A')}")

    st.sidebar.markdown("---")

    # Navigation choices
    if user["role"] == "student":
        menu = st.sidebar.radio(
            "Student Portal Navigation",
            [
                "🎓 College FAQ Assistant",
                "📜 My Inquiry History",
                "📝 Request a Document",
                "📁 My Document Requests"
            ]
        )
    else:
        menu = st.sidebar.radio(
            "Admin Portal Navigation",
            [
                "📊 Admin Dashboard",
                "📚 Knowledge Base",
                "⚖️ Pending Approvals",
                "📑 Document Requests",
                "🛡️ Admin Activity & Audit Log",
                "🩺 Authorized System Diagnostics"
            ]
        )

    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Sign Out", use_container_width=True):
        st.session_state.user = None
        st.rerun()

    return menu


# =====================================================================
# STUDENT VIEWS
# =====================================================================

def render_student_faq(user: dict):
    st.subheader("🎓 College FAQ Assistant")
    st.markdown(
        "Ask questions regarding **attendance regulations, examination schedules, library timings, "
        "bonafide certificates, fees, scholarships, and official policies** for DUM DUM Group of Institution."
    )

    # Topic Quick Filters
    st.caption("💡 Quick Frequently Asked Topics:")
    q_col1, q_col2, q_col3, q_col4 = st.columns(4)
    with q_col1:
        if st.button("📋 75% Attendance Rule"):
            st.session_state.current_question = "What is the minimum attendance requirement and medical condonation policy?"
    with q_col2:
        if st.button("🕒 Library Timings"):
            st.session_state.current_question = "What are the Central Library operational hours and book borrow limits?"
    with q_col3:
        if st.button("🌙 Hostel Curfew"):
            st.session_state.current_question = "What are the hostel curfew hours and night-out pass rules?"
    with q_col4:
        if st.button("📜 Bonafide Certificate"):
            st.session_state.current_question = "How do I get a Bonafide Certificate and how many days does it take?"

    user_query = st.text_area(
        "Enter your question for the College FAQ Agent:",
        value=st.session_state.current_question,
        placeholder="e.g. Can my attendance be condoned on medical grounds? What is the procedure?",
        height=90
    )

    if st.button("Ask College FAQ Agent", type="primary", use_container_width=True):
        if not user_query.strip():
            st.warning("Please enter a question.")
            return

        with st.spinner("Analyzing inquiry, searching published college documents, and verifying grounding..."):
            result = run_faq_pipeline(question=user_query, student_user=user)

        st.markdown("---")
        # Header Badge
        status = result.get("verification_status", "UNVERIFIED")
        if status == "VERIFIED_OFFICIAL":
            st.markdown(
                f"<div class='badge-verified'>✅ VERIFIED OFFICIAL POLICY — Grounded in Ratified Institutional Documents</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<div class='badge-unverified'>⚠️ UNVERIFIED BY OFFICIAL RECORDS — No Ratified Document Matches This Query</div>",
                unsafe_allow_html=True
            )

        st.markdown(f"**Domain Category:** `{result.get('category', 'General')}`")
        st.markdown(result["answer"])

        # Display Source Citations
        sources = result.get("sources", [])
        if sources:
            st.markdown("#### 📖 Official Document Citations")
            for idx, src in enumerate(sources, start=1):
                with st.expander(f"Source {idx}: {src['document_title']} (Page {src['page_number']})"):
                    st.markdown(f"**Original File:** `{src['filename']}`")
                    st.markdown(f"**Verified Excerpt:**")
                    st.info(src["snippet"])


def render_student_inquiry_history(user: dict):
    st.subheader("📜 My Inquiry History")
    st.caption("Review your past questions and grounded verified answers. Only your records are shown.")

    history = get_student_inquiry_history(user["id"])
    if not history:
        st.info("You have not asked any FAQ questions yet. Visit the College FAQ Assistant to get started!")
        return

    for item in history:
        status = item.get("verification_status", "UNVERIFIED")
        badge_class = "badge-verified" if status == "VERIFIED_OFFICIAL" else "badge-unverified"
        badge_text = "✅ VERIFIED OFFICIAL" if status == "VERIFIED_OFFICIAL" else "⚠️ UNVERIFIED"

        with st.container():
            st.markdown(f"""
            <div class="custom-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span class="{badge_class}">{badge_text}</span>
                    <span style="font-size: 0.8rem; color: #64748b;">{item['created_at']}</span>
                </div>
                <h4 style="margin: 0 0 6px 0; color: #0d233a;">Question: {item['question']}</h4>
                <div style="font-size: 0.85rem; color: #475569; margin-bottom: 8px;">Domain: <b>{item.get('category', 'General')}</b></div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("View Full Recorded Response & Sources"):
                st.markdown(item["answer"])
                sources = item.get("sources", [])
                if sources:
                    st.caption("Citations:")
                    for s in sources:
                        st.markdown(f"- **{s.get('document_title')}** (Page {s.get('page_number')})")


def render_student_request_document(user: dict):
    st.subheader("📝 Request an Official Institutional Document")
    st.markdown(
        "Submit a request for an official certificate. Our AI will formulate a standardized draft "
        "following DUM DUM Group of Institution administrative guidelines and submit it for **Registrar approval**."
    )

    with st.form("request_doc_form"):
        st.markdown("#### 1. Student Identification (Auto-filled from Records)")
        id_col1, id_col2 = st.columns(2)
        with id_col1:
            st.text_input("Student Full Name", value=user["full_name"], disabled=True)
            st.text_input("Department", value=user.get("department", "CSE"), disabled=True)
        with id_col2:
            st.text_input("Roll / Registration No.", value=user.get("roll_number", "DGD-000"), disabled=True)
            st.text_input("Year / Semester", value=user.get("year_semester", "Current"), disabled=True)

        st.markdown("#### 2. Request Specifics")
        doc_type_key = st.selectbox(
            "Select Certificate Type",
            options=list(SUPPORTED_DOCUMENT_TYPES.keys()),
            format_func=lambda k: SUPPORTED_DOCUMENT_TYPES[k]
        )

        purpose = st.text_area(
            "State Specific Purpose of Request * (Required)",
            placeholder="e.g. Required for Passport application verification / State Transport Bus Pass concession / Education loan processing",
            help="Specify exact organization or regulatory requirement."
        )

        supporting_notes = st.text_input(
            "Additional Notes or Reference Dates (Optional)",
            placeholder="e.g. Application deadline: 25th of this month"
        )

        submit_req = st.form_submit_button("Generate AI Draft & Submit for Approval", type="primary", use_container_width=True)

        if submit_req:
            if not purpose or len(purpose.strip()) < 5:
                st.error("Please provide a detailed purpose of at least 5 characters.")
                return

            with st.spinner("AI drafting agent is composing standardized institutional certificate draft..."):
                request_data = {
                    "doc_type": doc_type_key,
                    "student_name": user["full_name"],
                    "roll_number": user.get("roll_number", "N/A"),
                    "department": user.get("department", "Academics"),
                    "year_semester": user.get("year_semester", "Current"),
                    "purpose": purpose.strip(),
                    "supporting_notes": supporting_notes.strip() if supporting_notes else ""
                }
                # Run AI drafting agent
                ai_draft = run_document_drafting_pipeline(request_data)

                # Create request in DB
                new_req = create_document_request(
                    student_user=user,
                    doc_type=doc_type_key,
                    purpose=purpose.strip(),
                    supporting_notes=supporting_notes.strip() if supporting_notes else "",
                    draft_content=ai_draft
                )

            st.success(f"Request #{new_req['request_number']} successfully generated and submitted for administrative review!")
            st.info("Your request is now in status **PENDING_APPROVAL**. You can track it in 'My Document Requests'.")


def render_visual_certificate(req: dict, is_approved: bool = False):
    """Renders a formal visual institutional certificate card in the Streamlit UI."""
    doc_title = SUPPORTED_DOCUMENT_TYPES.get(req["doc_type"], "BONAFIDE CERTIFICATE").upper()
    date_str = req.get("approved_at", req["created_at"])[:10] if req.get("approved_at") else datetime.now().strftime("%B %d, %Y")

    raw_body = req["draft_content"]
    lines = []
    for line in raw_body.splitlines():
        l = line.strip()
        if l.startswith('---') or l.startswith('===') or l.startswith('___') or l.startswith('[Draft Prepared') or l.startswith('[Pending') or l.startswith('DOCUMENT TYPE:') or l.startswith('DATE:'):
            continue
        if l.startswith('**DUM DUM GROUP') or l.startswith('*Office of') or l.startswith('*Campus:') or l.startswith('*Website:'):
            continue
        if l.startswith('**Ref. No:') or l.startswith('**Date:'):
            continue
        if l.startswith('###') or l.startswith('##') or l.startswith('#'):
            continue
        if 'Registrar / Administrative Officer' in l or 'Dr. Alok Banerjee' in l:
            continue
        if '[Official Institutional Seal' in l:
            continue
        lines.append(l)

    body_text = "\n".join(lines).strip() or f"This is to certify that {req['student_name']} (Roll No: {req['roll_number']}) is a bona fide student of {COLLEGE_NAME}, currently enrolled in the Department of {req['department']} ({req['year_semester']}). This certificate is issued upon student request for the purpose of: {req['purpose']}."
    # Clean markdown bold/italic for HTML display
    import re
    body_html_formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', body_text)
    body_html_formatted = re.sub(r'\*(.*?)\*', r'<i>\1</i>', body_html_formatted)
    body_html = body_html_formatted.replace("\n\n", "</p><p>").replace("\n", "<br/>")

    seal_block = f"""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-top: 25px; padding-top: 15px; border-top: 1px solid #cbd5e1;">
        <div style="text-align: left;">
            <div style="border: 2px solid #059669; background: #ecfdf5; color: #065f46; padding: 6px 12px; border-radius: 6px; font-size: 0.82rem; font-weight: bold; font-family: sans-serif;">
                🛡️ DIGITALLY VERIFIED & ISSUED<br/>
                <span style="font-size: 0.7rem; font-weight: normal; color: #047857;">Security Hash: SHA256-{req.get('content_hash', '')[:16]}<br/>
                Issued: {req.get('approved_at', 'Official Record')}</span>
            </div>
        </div>
        <div style="text-align: right; font-family: sans-serif;">
            <div style="font-family: 'Brush Script MT', cursive, serif; font-size: 1.6rem; color: #0d233a; margin-bottom: 2px;">Dr. Alok Banerjee</div>
            <div style="font-size: 0.85rem; font-weight: bold; color: #0d233a;">Dr. Alok Banerjee</div>
            <div style="font-size: 0.75rem; color: #64748b;">Registrar & Controller of Services<br/>{COLLEGE_NAME}</div>
        </div>
    </div>
    """ if is_approved else f"""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-top: 25px; padding-top: 15px; border-top: 1px dashed #cbd5e1;">
        <div style="text-align: left;">
            <div style="border: 2px dashed #d97706; background: #fffbeb; color: #92400e; padding: 6px 12px; border-radius: 6px; font-size: 0.82rem; font-weight: bold; font-family: sans-serif;">
                ⏳ PENDING REGISTRAR APPROVAL<br/>
                <span style="font-size: 0.7rem; font-weight: normal; color: #b45309;">Draft Content Hash: {req.get('content_hash', '')[:16]}</span>
            </div>
        </div>
        <div style="text-align: right; font-family: sans-serif;">
            <div style="font-size: 0.8rem; color: #94a3b8; font-style: italic;">[Awaiting Registrar Verification & Digital Seal]</div>
            <div style="font-size: 0.75rem; color: #64748b;">Office of the Registrar<br/>{COLLEGE_NAME}</div>
        </div>
    </div>
    """

    cert_html = f"""
    <div style="border: 4px double #b45309; background: #fffdfa; padding: 2rem 2.2rem; border-radius: 10px; box-shadow: 0 4px 18px rgba(13, 35, 58, 0.08); margin: 1rem 0; font-family: 'Georgia', serif;">
        <div style="text-align: center; border-bottom: 2px solid #0d233a; padding-bottom: 10px; margin-bottom: 12px;">
            <div style="font-size: 0.8rem; letter-spacing: 2px; font-weight: bold; color: #d97706; text-transform: uppercase; font-family: sans-serif;">Official Institutional Certificate</div>
            <h2 style="margin: 4px 0; color: #0d233a; font-family: 'Helvetica', sans-serif; font-size: 1.55rem; letter-spacing: 0.5px;">{COLLEGE_NAME.upper()}</h2>
            <div style="font-size: 0.78rem; color: #64748b; font-family: sans-serif;">{COLLEGE_TAGLINE} | Institutional Code: <b>{COLLEGE_CODE}</b></div>
        </div>

        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #475569; margin-bottom: 12px; font-family: sans-serif;">
            <div><b>Ref. No:</b> {req['request_number']}</div>
            <div><b>Date:</b> {date_str}</div>
        </div>

        <div style="text-align: center; margin: 12px 0 16px 0;">
            <h3 style="color: #b45309; margin: 0; font-size: 1.25rem; letter-spacing: 1.2px; text-decoration: underline; text-underline-offset: 5px;">{doc_title}</h3>
        </div>

        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; margin-bottom: 15px; font-family: sans-serif; font-size: 0.82rem;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                <div><b>Student Name:</b> {req['student_name']}</div>
                <div><b>Roll / Reg. No:</b> {req['roll_number']}</div>
                <div><b>Department:</b> {req['department']}</div>
                <div><b>Academic Year / Sem:</b> {req['year_semester']}</div>
            </div>
        </div>

        <div style="font-size: 0.98rem; line-height: 1.75; color: #1e293b; text-align: justify; margin-bottom: 15px;">
            <p>{body_html}</p>
        </div>

        {seal_block}
    </div>
    """
    st.markdown(cert_html, unsafe_allow_html=True)


def render_student_my_requests(user: dict):
    st.subheader("📁 My Document Requests")
    st.caption("Track the status of your document requests, inspect the AI-generated certificate, and download your official approved PDF.")

    requests = get_student_document_requests(user["id"])
    if not requests:
        st.info("You have not submitted any document requests yet. Use 'Request a Document' to generate a Bonafide Certificate.")
        return

    for req in requests:
        status = req["status"]
        if status == "APPROVED":
            badge_html = "<span class='badge-approved'>✅ APPROVED</span>"
        elif status == "REJECTED":
            badge_html = "<span class='badge-rejected'>❌ REJECTED</span>"
        else:
            badge_html = "<span class='badge-pending'>⏳ PENDING APPROVAL</span>"

        with st.container():
            st.markdown(f"""
            <div class="custom-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div><b style="font-size: 1.05rem;">Ref: {req['request_number']}</b> | {SUPPORTED_DOCUMENT_TYPES.get(req['doc_type'], req['doc_type'])}</div>
                    <div>{badge_html}</div>
                </div>
                <div style="font-size: 0.85rem; color: #475569;">
                    <b>Certified Purpose:</b> {req['purpose']}<br/>
                    <b>Submitted on:</b> {req['created_at']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Auto-compile PDF if approved but file missing
            pdf_data = None
            pdf_ready = False
            if status == "APPROVED":
                from document_service import generate_approved_pdf_for_request
                pdf_file_path = req.get("pdf_path")
                if not pdf_file_path or not Path(pdf_file_path).exists():
                    admin_stub = {"id": req.get("approved_by") or 1, "username": "admin", "full_name": "Dr. Alok Banerjee (Registrar)", "role": "admin"}
                    generate_approved_pdf_for_request(req["id"], admin_stub)
                    # refresh record
                    refreshed = get_request_by_id(req["id"])
                    pdf_file_path = refreshed.get("pdf_path")

                if pdf_file_path and Path(pdf_file_path).exists():
                    pdf_data = Path(pdf_file_path).read_bytes()
                    pdf_ready = True

            # Action bar: prominent download button
            if status == "APPROVED" and pdf_ready:
                col_btn, col_info = st.columns([1, 2])
                with col_btn:
                    st.download_button(
                        label="📥 Download Official Signed PDF",
                        data=pdf_data,
                        file_name=f"{req['request_number']}.pdf",
                        mime="application/pdf",
                        key=f"dl_cert_{req['id']}",
                        type="primary",
                        use_container_width=True
                    )
                with col_info:
                    st.success("✅ This certificate is officially approved, signed, and stamped by the Registrar!")
            elif status == "REJECTED":
                st.error(f"❌ Certificate request rejected by administration. Reason: {req.get('admin_feedback', 'Disapproved')}")
            else:
                st.warning("⏳ This draft certificate is currently awaiting administrative approval in the Registrar queue.")

            # Visual Certificate Rendering
            with st.expander(f"📜 View {SUPPORTED_DOCUMENT_TYPES.get(req['doc_type'], 'Certificate')} (Visual Document)", expanded=(status == "APPROVED")):
                render_visual_certificate(req, is_approved=(status == "APPROVED"))


# =====================================================================
# ADMIN VIEWS
# =====================================================================

def render_admin_dashboard(user: dict):
    st.subheader("📊 Administrative Overview Dashboard")
    st.markdown(f"Central command center for **{COLLEGE_NAME}** Knowledge Base and Approval workflows.")

    # Fetch stats
    docs = get_all_documents()
    published_docs = [d for d in docs if d.get("status") == "PUBLISHED"]
    pending_approvals = get_pending_approvals()
    all_requests = get_all_document_requests()
    pending_requests = [r for r in all_requests if r.get("status") == "PENDING_APPROVAL"]

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM faq_inquiries")
        total_faqs = cursor.fetchone()[0]

    # Metrics row
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"""
        <div class="stat-metric-card">
            <div class="stat-metric-val">{len(docs)}</div>
            <div class="stat-metric-lbl">Total Documents</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
        <div class="stat-metric-card">
            <div class="stat-metric-val">{len(published_docs)}</div>
            <div class="stat-metric-lbl">Published Sources</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="stat-metric-card" style="border-top-color: #d97706;">
            <div class="stat-metric-val">{len(pending_approvals)}</div>
            <div class="stat-metric-lbl">Pending Approvals</div>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="stat-metric-card">
            <div class="stat-metric-val">{len(pending_requests)}</div>
            <div class="stat-metric-lbl">Open Doc Requests</div>
        </div>
        """, unsafe_allow_html=True)
    with m5:
        st.markdown(f"""
        <div class="stat-metric-card">
            <div class="stat-metric-val">{total_faqs}</div>
            <div class="stat-metric-lbl">FAQs Answered</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### ⚡ Quick Operations")
    q1, q2, q3 = st.columns(3)
    with q1:
        st.info(f"**Knowledge Base:** {len(published_docs)} of {len(docs)} documents are published as official student sources.")
    with q2:
        st.warning(f"**HITL Queue:** {len(pending_approvals)} actions require explicit human administrative verification.")
    with q3:
        st.success(f"**Active AI Engine:** Google Gemini (`{get_active_model_name()}`) connected.")


def render_admin_knowledge_base(user: dict):
    st.subheader("📚 Knowledge Base Management")
    st.markdown(
        "Upload official college circulars, notices, and handbook documents (PDF, PNG, JPG, JPEG). "
        "The system extracts text/OCR, runs Gemini analysis, and creates semantic chunks. "
        "**Only approved and published documents may be used as verified official sources for student answers.**"
    )

    tab_upload, tab_manage = st.tabs(["📤 Upload New College Document", "📑 Manage Existing Documents"])

    with tab_upload:
        st.markdown("#### Upload Official Institutional Document")
        uploaded_file = st.file_uploader(
            "Choose a document (PDF, PNG, JPG, JPEG - max 15MB)",
            type=["pdf", "png", "jpg", "jpeg"]
        )

        doc_title = st.text_input(
            "Document Title *",
            placeholder="e.g. Academic Calendar & Holiday Schedule 2026-27"
        )

        run_ai = st.checkbox("Perform Gemini Document Analysis (Summary, Topic & Rule Extraction)", value=True)

        if st.button("Upload & Process Document", type="primary"):
            if not uploaded_file:
                st.error("Please select a file to upload.")
                return
            if not doc_title.strip():
                st.error("Please provide a title for the document.")
                return

            file_bytes = uploaded_file.read()
            valid, msg = validate_file(uploaded_file.name, file_bytes)
            if not valid:
                st.error(msg)
                return

            with st.spinner("Saving file, extracting text/OCR, generating chunks, and analyzing with Gemini..."):
                saved_path, sanitized_orig = save_uploaded_file(uploaded_file.name, file_bytes)
                doc_record = add_document(
                    file_path=saved_path,
                    original_filename=sanitized_orig,
                    title=doc_title.strip(),
                    uploaded_by_user_id=user["id"],
                    uploaded_by_username=user["username"],
                    run_ai_analysis=run_ai
                )

            st.success(f"Document '{doc_title}' successfully uploaded and indexed with ID #{doc_record['id']}!")
            st.info("The document is currently in **PENDING_REVIEW** status. You must review and publish it before it becomes active in student FAQ retrieval.")

    with tab_manage:
        st.markdown("#### Published and Pending Knowledge Sources")
        status_filter = st.selectbox("Filter by Status", ["ALL", "PUBLISHED", "PENDING_REVIEW", "UNPUBLISHED", "REPLACED"])
        all_docs = get_all_documents(filter_status=status_filter)

        if not all_docs:
            st.info("No documents found matching this filter.")
            return

        for doc in all_docs:
            st.markdown("---")
            status = doc["status"]
            if status == "PUBLISHED":
                badge_html = "<span class='badge-approved'>✅ PUBLISHED (Official Source)</span>"
            elif status == "PENDING_REVIEW":
                badge_html = "<span class='badge-pending'>⏳ PENDING REVIEW</span>"
            elif status == "REPLACED":
                badge_html = "<span class='badge-rejected'>🔄 REPLACED</span>"
            else:
                badge_html = "<span class='badge-rejected'>⛔ UNPUBLISHED</span>"

            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4 style="margin: 0; color: #0d233a;">#{doc['id']} - {doc['title']} (v{doc['version']})</h4>
                <div>{badge_html}</div>
            </div>
            <div style="font-size: 0.82rem; color: #64748b; margin-top: 4px;">
                File: <code>{doc['original_filename']}</code> | Pages: {doc['page_count']} | Uploaded: {doc['upload_date']}
            </div>
            """, unsafe_allow_html=True)

            # Details & Actions
            act_col1, act_col2 = st.columns([3, 1])
            with act_col1:
                with st.expander("Inspect Document Analysis & Extracted Chunks"):
                    st.markdown("**Executive Summary:**")
                    st.write(doc.get("summary") or "No summary available.")
                    st.markdown(f"**Topics Identified:** `{', '.join(doc.get('topics_list', []))}`")
                    st.markdown("**Extracted Rules & Policies:**")
                    for r in doc.get("rules_list", []):
                        st.markdown(f"- {r}")

                    st.markdown("---")
                    chunks = get_document_chunks(doc["id"])
                    st.caption(f"Semantic Chunks ({len(chunks)}):")
                    for ch in chunks[:3]:
                        st.text(f"Chunk {ch['chunk_index']} (Page {ch['page_number']}): {ch['content'][:150]}...")

            with act_col2:
                if status == "PENDING_REVIEW" or status == "UNPUBLISHED":
                    if st.button("Publish as Official Source", key=f"pub_{doc['id']}", use_container_width=True):
                        publish_document(doc["id"], user, review_notes="Admin verified and ratified content.")
                        st.success(f"Published document #{doc['id']}!")
                        st.rerun()

                if status == "PUBLISHED":
                    if st.button("Unpublish Document", key=f"unpub_{doc['id']}", use_container_width=True):
                        unpublish_document(doc["id"], user, reason="Admin unpublished from active retrieval.")
                        st.warning(f"Unpublished document #{doc['id']}.")
                        st.rerun()

                if st.button("Re-index Document", key=f"reidx_{doc['id']}", use_container_width=True):
                    with st.spinner("Re-indexing chunks and re-analyzing..."):
                        reindex_document(doc["id"], user)
                    st.success("Re-indexed successfully.")
                    st.rerun()


def render_admin_pending_approvals(user: dict):
    st.subheader("⚖️ Human-in-the-Loop Pending Approvals")
    st.markdown(
        "Critical backend-enforced approval hub. "
        "**AI agents can never approve actions on their own. Official document issuance, email delivery, and knowledge base alterations require explicit human administrative verification.**"
    )

    approvals = get_pending_approvals()
    if not approvals:
        st.success("🎉 No pending actions in the approval queue! All tasks are up to date.")
        return

    st.markdown(f"Showing **{len(approvals)}** pending administrative decision(s):")

    for app in approvals:
        st.markdown("---")
        app_id = app["id"]
        action_type = app["action_type"]
        target_entity = app["target_entity"]
        target_id = app["target_id"]

        st.markdown(f"""
        <div class="custom-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span class="badge-pending">ACTION ID #{app_id}: {action_type}</span>
                <span style="font-size: 0.8rem; color: #64748b;">Requested: {app['created_at']}</span>
            </div>
            <div><b>Target:</b> {target_entity} #{target_id} | <b>Requester:</b> {app['requester_name']} ({app['requester_username']})</div>
            <div style="font-size: 0.8rem; color: #64748b; margin-top: 4px;">Payload Security Hash: <code>{app['payload_hash'][:20]}...</code></div>
        </div>
        """, unsafe_allow_html=True)

        # Context details
        if target_entity == "document_requests":
            req_data = get_request_by_id(target_id)
            if req_data:
                st.markdown(f"**Student:** {req_data['student_name']} ({req_data['roll_number']}) | **Document:** {req_data['doc_type']}")
                st.markdown(f"**Certified Purpose:** {req_data['purpose']}")
                with st.expander("Inspect Full AI-Prepared Certificate Draft"):
                    st.text(req_data["draft_content"])

        col_left, col_right = st.columns([1, 1])
        with col_left:
            review_notes = st.text_input("Approval / Verification Notes", key=f"notes_{app_id}", placeholder="e.g. Verified records; approved for issuance.")
            if st.button("✅ Approve & Execute Action", key=f"btn_app_{app_id}", type="primary", use_container_width=True):
                ok, msg = approve_action(app_id, user, review_notes=review_notes)
                if ok:
                    st.success(f"Action #{app_id} approved and executed: {msg}")
                    st.rerun()
                else:
                    st.error(f"Approval failed: {msg}")

        with col_right:
            reject_reason = st.text_input("Rejection Reason", key=f"rej_{app_id}", placeholder="e.g. Missing required attachment or invalid purpose.")
            if st.button("❌ Reject Action", key=f"btn_rej_{app_id}", use_container_width=True):
                reject_action(app_id, user, reason=reject_reason or "Rejected by administrator")
                st.warning(f"Action #{app_id} rejected.")
                st.rerun()


def render_admin_document_requests(user: dict):
    st.subheader("📑 Student Document Requests Manager")
    st.caption("Manage, review, edit drafts, and track all institutional student document requests.")

    filter_status = st.selectbox("Status Filter", ["ALL", "PENDING_APPROVAL", "APPROVED", "REJECTED"], key="req_filter")
    requests = get_all_document_requests(filter_status=filter_status)

    if not requests:
        st.info("No document requests found.")
        return

    for req in requests:
        st.markdown("---")
        status = req["status"]
        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h4 style="margin: 0; color: #0d233a;">Ref: {req['request_number']} — {req['student_name']} ({req['roll_number']})</h4>
            <span class="badge-{status.lower()}">{status}</span>
        </div>
        <div style="font-size: 0.85rem; color: #475569; margin-top: 4px;">
            <b>Type:</b> {SUPPORTED_DOCUMENT_TYPES.get(req['doc_type'], req['doc_type'])} | <b>Dept:</b> {req['department']} | <b>Purpose:</b> {req['purpose']}
        </div>
        """, unsafe_allow_html=True)

        edit_exp = st.expander("Review / Edit Draft Content")
        with edit_exp:
            st.caption("Editing draft content automatically updates the security hash and invalidates any previous approval.")
            edited_text = st.text_area("Draft Certificate Text:", value=req["draft_content"], height=160, key=f"edit_draft_{req['id']}")
            if st.button("Save Draft Modifications", key=f"save_edit_{req['id']}"):
                update_request_draft(req["id"], edited_text, user)
                st.success("Draft updated. Status reset to PENDING_APPROVAL for re-review.")
                st.rerun()

        if status == "APPROVED" and req.get("pdf_path"):
            pdf_path = Path(req["pdf_path"])
            if pdf_path.exists():
                st.download_button(
                    label=f"📥 Download Compiled PDF ({req['request_number']}.pdf)",
                    data=pdf_path.read_bytes(),
                    file_name=f"{req['request_number']}.pdf",
                    mime="application/pdf",
                    key=f"adm_dl_{req['id']}"
                )


def render_admin_audit_log(user: dict):
    st.subheader("🛡️ Administrative Activity & Audit Log")
    st.markdown(
        "Immutable, append-only security and operational audit trail. "
        "Records all document uploads, publishing decisions, student inquiries, approvals, and dispatches."
    )

    # Filters
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        f_sev = st.selectbox("Severity Level", ["ALL", "INFO", "WARNING", "SECURITY", "AUDIT"])
    with f2:
        f_act = st.text_input("Filter by Action Keyword", placeholder="e.g. LOGIN, DOCUMENT, HITL")
    with f3:
        d_from = st.date_input("From Date", value=None)
    with f4:
        d_to = st.date_input("To Date", value=None)

    date_from_str = d_from.strftime("%Y-%m-%d") if d_from else None
    date_to_str = d_to.strftime("%Y-%m-%d") if d_to else None

    logs = get_audit_logs(
        filter_severity=f_sev,
        filter_action=f_act,
        date_from=date_from_str,
        date_to=date_to_str,
        limit=200
    )

    # Safe CSV Export with formula injection protection
    csv_data = export_audit_logs_csv(logs)
    st.download_button(
        label="📥 Export Sanitized Audit Log (CSV)",
        data=csv_data,
        file_name=f"dumdum_audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        help="Protected against CSV formula injection (CWE-1236)."
    )

    if not logs:
        st.info("No audit logs found matching criteria.")
        return

    # Render table
    df = pd.DataFrame(logs)
    display_cols = ["id", "timestamp", "actor_username", "actor_role", "action", "target_entity", "details", "severity"]
    available_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available_cols], use_container_width=True, hide_index=True)


def render_admin_diagnostics(user: dict):
    st.subheader("🩺 Authorized System Diagnostics")
    st.markdown("Real-time operational health checks for API endpoints, models, database, and background agents.")

    diag_col1, diag_col2 = st.columns(2)

    with diag_col1:
        st.markdown("#### 1. Google Gemini API Status")
        has_key = bool(GEMINI_API_KEY)
        st.markdown(f"**Gemini API Key Configured:** `{'✅ YES' if has_key else '❌ NO'}`")
        st.markdown(f"**Active CrewAI LLM Model:** `{get_active_model_name()}`")
        st.markdown(f"**Configured Primary Model:** `{PRIMARY_MODEL}`")

        # Live connectivity test button
        if st.button("Test Gemini Model Connectivity"):
            with st.spinner("Connecting to Google Gemini API..."):
                try:
                    from google import genai
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    resp = client.models.generate_content(
                        model=get_active_model_name(),
                        contents="Respond with only: SYSTEM_ONLINE"
                    )
                    st.success(f"Connection Successful! Gemini Response: {resp.text.strip()}")
                except Exception as e:
                    st.error(f"Gemini Connectivity Error: {str(e)}")

        st.markdown("#### 2. Email / SMTP Dispatch Status")
        st.markdown(f"**SMTP Delivery Enabled:** `{'✅ ENABLED' if SMTP_ENABLED else '⚠️ DISABLED (Simulated Safe Mode)'}`")
        st.caption("Human-in-the-Loop enforces that all external emails must be explicitly reviewed and approved by an administrator before dispatch.")

    with diag_col2:
        st.markdown("#### 3. Database & Storage Health")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users;")
            users_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM documents;")
            docs_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM document_chunks;")
            chunks_count = cursor.fetchone()[0]

        st.markdown(f"**SQLite Database Mode:** `{journal_mode.upper()}` (Write-Ahead Logging)")
        st.markdown(f"**Users Registered:** `{users_count}`")
        st.markdown(f"**Documents Stored:** `{docs_count}`")
        st.markdown(f"**Search Chunks Indexed:** `{chunks_count}`")

        st.markdown("#### 4. Document Processing Engines")
        from document_processor import PYMUPDF_AVAILABLE, PYPDF_AVAILABLE, PYTESSERACT_AVAILABLE
        st.markdown(f"**PyMuPDF (fitz) Engine:** `{'✅ Available' if PYMUPDF_AVAILABLE else '❌ Missing'}`")
        st.markdown(f"**pypdf Engine:** `{'✅ Available' if PYPDF_AVAILABLE else '❌ Missing'}`")
        st.markdown(f"**Tesseract OCR Engine:** `{'✅ Available' if PYTESSERACT_AVAILABLE else 'ℹ️ Using Gemini Vision OCR'}`")


# =====================================================================
# MAIN ENTRYPOINT
# =====================================================================

def main():
    if not st.session_state.user:
        render_login_register()
        return

    # Render Header Banner
    st.markdown(f"""
    <div class="college-header-banner">
        <h1 class="college-header-title">🏛️ {COLLEGE_NAME}</h1>
        <p class="college-header-tagline">{COLLEGE_TAGLINE} | Institutional Portal ({COLLEGE_CODE})</p>
    </div>
    """, unsafe_allow_html=True)

    # Render Sidebar and Route
    menu = render_sidebar()
    user = st.session_state.user

    if user["role"] == "student":
        if menu == "🎓 College FAQ Assistant":
            render_student_faq(user)
        elif menu == "📜 My Inquiry History":
            render_student_inquiry_history(user)
        elif menu == "📝 Request a Document":
            render_student_request_document(user)
        elif menu == "📁 My Document Requests":
            render_student_my_requests(user)
    else:
        if menu == "📊 Admin Dashboard":
            render_admin_dashboard(user)
        elif menu == "📚 Knowledge Base":
            render_admin_knowledge_base(user)
        elif menu == "⚖️ Pending Approvals":
            render_admin_pending_approvals(user)
        elif menu == "📑 Document Requests":
            render_admin_document_requests(user)
        elif menu == "🛡️ Admin Activity & Audit Log":
            render_admin_audit_log(user)
        elif menu == "🩺 Authorized System Diagnostics":
            render_admin_diagnostics(user)


if __name__ == "__main__":
    main()
