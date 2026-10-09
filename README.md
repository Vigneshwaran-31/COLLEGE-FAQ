# 🏛️ DUM DUM Group of Institution — College FAQ Agent & Administrative Approval Portal

An enterprise-grade, institutional **College FAQ Agent with AI-Powered Knowledge Base and Human-in-the-Loop Approval** built from scratch for **DUM DUM Group of Institution** (`DGD-2026`).

This application focuses strictly on answering student inquiries regarding official college policies, analyzing verified institutional regulatory circulars, managing student inquiries, and preparing student document requests for administrative review and official sealed PDF issuance.

---

## 🌟 Core Highlights & Architectural Principles

1. **Multi-Agent CrewAI Architecture**
   - **Question Analysis Agent**: Breaks down student questions into institutional domains (Attendance, Examinations, Fees, Scholarships, Library, Hostel, Bonafide, Office Hours), extracts constraints and query terms.
   - **College FAQ Retrieval Agent**: Interacts with the published Knowledge Base using dedicated retrieval tools (`KnowledgeBaseSearchTool`, `CollegePolicyLookupTool`) to extract exact regulatory clauses and page numbers.
   - **Answer Verification Agent**: Audits grounding with strict compliance rules. Ensures answers are 100% supported by official text, cites document titles and page numbers, and explicitly marks unsupported questions as `UNVERIFIED BY OFFICIAL RECORDS`.
   - **Document Request Drafting Agent**: Prepares standardized institutional certificate drafts (Bonafide, Study Certificate, Permission Letter, Fee Structure) following administrative templates without hallucinating student data or signatures.

2. **Google Gemini LLM Integration**
   - Built for Google Gemini (`gemini-2.5-flash` with resilient fallback to `gemini-3.5-flash` / `gemini-3.5-flash-lite`).
   - Resilient error handling: detects and handles rate/quota limits (`429 RESOURCE_EXHAUSTED`) safely without infinite retry loops, and provides direct grounded synthesis when quota is reached.

3. **Strict Human-in-the-Loop (HITL) Approval Enforcement**
   - **Official Document Issuance**: Student document requests start in `PENDING_APPROVAL`. AI agents can NEVER approve their own proposals. Final ReportLab PDF generation executes **ONLY IF** an authenticated human administrator approves the request.
   - **Approval Invalidation**: If draft content is modified after an approval, the previous approval is automatically invalidated, and the request reverts to `PENDING_APPROVAL`.
   - **External Email Delivery**: Emails are prepared into an `email_queue` and require explicit admin approval before dispatch. If SMTP is not configured in `.env`, the system explicitly reports that delivery is unavailable rather than simulating false success.
   - **Publishing Gatekeeper**: Uploaded documents enter `PENDING_REVIEW` and are strictly excluded from student search until an administrator verifies and publishes them.

4. **Institutional Security & Data Isolation**
   - **Student Access Isolation**: Backend queries and authorization checks prevent students from viewing or downloading another student's inquiry logs or compiled certificates.
   - **Audit Log Immutability**: All uploads, verifications, approvals, rejections, PDF compilations, and queries are recorded in an append-only audit trail.
   - **Formula Injection Defense (CWE-1236)**: Admin CSV audit exports automatically sanitize spreadsheet formula triggers (`=`, `+`, `-`, `@`, tab).

---

## 🛠️ Technology Stack

| Technology | Purpose |
| :--- | :--- |
| **Python 3.13 / 3.11+** | Backend application core |
| **Streamlit** | Interactive institutional UI with role-based navigation |
| **CrewAI** | Multi-agent collaboration framework |
| **Google Gemini** | LLM reasoning engine (`gemini-2.5-flash` / `gemini-3.5-flash`) |
| **PyMuPDF (`fitz`) & pypdf** | Page-by-page PDF text extraction and rasterization |
| **Pillow & Gemini Vision / OCR** | Multimodal OCR for scanned documents, notices, and images |
| **SQLite (WAL Mode)** | Persistent ACID database with zero-config local storage |
| **ReportLab** | Formal institutional certificate and letterhead PDF compilation |
| **python-dotenv** | Environment and secret configuration |
| **pytest** | Automated test suite (25/25 passing unit and integration tests) |

---

## 🚀 Beginner-Friendly Windows Installation Guide

### Prerequisites
- Windows 10 or Windows 11
- Python 3.10 to 3.13 installed ([python.org](https://www.python.org/downloads/)). *Make sure to check "Add Python to PATH" during installation.*

### Step 1: Open PowerShell in Project Directory
Navigate to the project folder:
```powershell
cd "c:\Users\admin\Documents\COLLEGE FAQ!"
```

### Step 2: Create and Activate Virtual Environment (Optional but Recommended)
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Open `.env` in any text editor and supply your Google Gemini API key:
```ini
GEMINI_API_KEY=AIzaSy...your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-3.5-flash,gemini-3.5-flash-lite
COLLEGE_NAME="DUM DUM Group of Institution"
COLLEGE_TAGLINE="Excellence in Education, Research & Integrity"
COLLEGE_CODE="DGD-2026"
```

### Step 5: Seed Official College Policy Documents (One-time)
Run the seed script to generate sample official PDFs in `sample_docs/` and publish them into the SQLite database:
```powershell
python seed_sample_documents.py
```
This generates and publishes four ratified institutional documents:
1. `Attendance_and_Leave_Regulations_2026.pdf` (Minimum 75% attendance rule, 65%-74% medical condonation, detention criteria, biometric hours)
2. `Examination_Grading_and_Evaluation_Code_2026.pdf` (Mid-term 8th week, end-sem 16th week, admit card criteria, Rs. 500 re-evaluation)
3. `Fees_Scholarships_and_Hostel_Manual_2026.pdf` (Due date 10th, Rs. 100/day fine, 9:00 PM hostel curfew, mess schedule)
4. `Bonafide_Certificates_and_Student_Services_Handbook_2026.pdf` (Bonafide turnaround 2 days, library 8 AM - 8 PM, borrow limits, office timings)

### Step 6: Launch the Streamlit Portal
Start the web application with:
```powershell
streamlit run app.py
```
Streamlit will launch locally at `http://localhost:8501`.

---

## 🔑 Pre-Configured Demo Accounts

| Role | Username | Password | Full Name & Details |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `Admin@123` | Dr. Alok Banerjee (Registrar & Controller of Services) |
| **Student 1** | `student1` | `Student@123` | Rahul Sharma (Roll: `DGD/2024/CSE-042`, Dept: CSE) |
| **Student 2** | `student2` | `Student@123` | Priya Patel (Roll: `DGD/2024/ECE-018`, Dept: ECE) |

*The login page also provides 1-click **Quick-Fill Demo Credentials** buttons for instant testing.*

---

## 🧭 Navigation & Feature Walkthrough

### 🎓 Student Portal Navigation
- **🎓 College FAQ Assistant**:
  - Ask natural language questions about attendance, exams, library, bonafide, fees, hostels.
  - Interactive quick-topic buttons for common inquiries.
  - Displays verified grounded answers with institutional verification badge (`✅ VERIFIED OFFICIAL` or `⚠️ UNVERIFIED`).
  - Expandable citation cards show exact document titles, page numbers, and verified excerpts.
- **📜 My Inquiry History**:
  - Personal log of past questions and verified answers.
  - Filter by domain and review past official citations.
- **📝 Request a Document**:
  - Request Bonafide Certificate, Study & Conduct Certificate, Permission Letter, or Fee Structure Statement.
  - Details auto-filled from institutional records.
  - CrewAI Document Request Drafting Agent prepares standardized draft.
  - Submits request to Admin Approval Dashboard with unique Request ID (`DOC-2026-XXXX`).
- **📁 My Document Requests**:
  - Live status tracking (`PENDING_APPROVAL`, `APPROVED`, `REJECTED`).
  - View draft and administrator feedback.
  - Secure **Download Official PDF** button enabled **ONLY when request is approved**.

### 👨‍💼 Administrator Portal Navigation
- **📊 Admin Dashboard**:
  - Overview statistics: Total Documents, Published Official Sources, Pending Approvals, Open Requests, FAQs Answered.
- **📚 Knowledge Base**:
  - Upload PDF, PNG, JPG, JPEG documents (up to 15MB).
  - Inspect Gemini AI summary, extracted topic tags, rules, and dates.
  - Document management: **Publish as Official Source**, **Unpublish Document**, **Replace with Revision**, and **Re-index**.
- **⚖️ Pending Approvals (Human-in-the-Loop Hub)**:
  - Unified queue for Document Issuance, Email Delivery, and Knowledge Base alterations.
  - Review student details, certified purpose, and AI draft preview.
  - Approve with notes (compiles official sealed PDF with cryptographic hash) or Reject with feedback.
- **📑 Document Requests**:
  - Comprehensive management table for all student requests.
  - Option to edit draft text (automatically updates hash and invalidates prior approvals).
- **🛡️ Admin Activity & Audit Log**:
  - Append-only security audit trail.
  - Filter by date, severity, action keyword, and actor.
  - Safe CSV export with formula injection protection (CWE-1236).
- **🩺 Authorized System Diagnostics**:
  - Real-time diagnostics for Google Gemini API key, active model resolution, SQLite database WAL mode, and PDF engines.

---

## 🧪 Automated Testing

The project includes an automated test suite covering all functional and security requirements.

To run the complete test suite:
```powershell
python -m pytest -v
```

### Test Coverage Summary (25/25 Passing):
- `tests/test_agents_and_workflow.py`: Grounded answers for known queries, unverified handling for unknown queries, citation tracking, student data isolation, Gemini quota limit (429) safety.
- `tests/test_approval_service.py`: AI agent self-approval prevention, payload tampering detection, email approval enforcement.
- `tests/test_audit_service.py`: Append-only logging, severity filtering, CSV formula injection defense.
- `tests/test_auth_service.py`: User authentication, registration validation, role checking, student isolation enforcement.
- `tests/test_database.py`: Table schema creation, foreign key constraints, default user seeding, password hashing.
- `tests/test_document_processor.py`: Allowed file extensions, size limits, PyMuPDF extraction, image OCR handling, chunking, heuristic analysis.
- `tests/test_document_service.py`: Document request lifecycle, content hashing, approved PDF generation, rejected request safety, approval invalidation upon edit, secure PDF downloads.
- `tests/test_knowledge_base.py`: Publishing gatekeeper (unapproved documents never returned in search), versioning, replacement, unpublishing.

---

## 📂 Project Directory Structure

```text
COLLEGE FAQ!/
├── .env.example               # Configuration template
├── .gitignore                  # Git exclusion rules
├── requirements.txt            # Python dependencies
├── config.py                   # Central configuration & paths
├── database.py                 # SQLite schema, WAL mode, migrations, seeds
├── auth_service.py             # Authentication & backend access control
├── audit_service.py            # Append-only audit logs & safe CSV export
├── document_processor.py       # PDF extraction, OCR, chunking & Gemini analysis
├── knowledge_base.py           # Document lifecycle, versioning & verified RAG search
├── approval_service.py         # Human-in-the-Loop approval state machine & guards
├── document_service.py         # Document request lifecycle & ReportLab PDF generator
├── tools.py                    # CrewAI knowledge retrieval tools
├── agents.py                   # CrewAI multi-agent definitions with Gemini LLM
├── tasks.py                    # CrewAI task specifications
├── workflow.py                 # Multi-agent workflow orchestrator & quota resilience
├── seed_sample_documents.py    # Seed generator for official college policy PDFs
├── app.py                      # Complete Streamlit Student & Admin application
├── sample_docs/                # Official college regulatory PDF documents
├── data/                       # Local SQLite DB, uploads, and generated PDFs
└── tests/                      # Automated test suite (25 tests)
    ├── conftest.py
    ├── test_database.py
    ├── test_auth_service.py
    ├── test_document_processor.py
    ├── test_knowledge_base.py
    ├── test_approval_service.py
    ├── test_document_service.py
    ├── test_audit_service.py
    └── test_agents_and_workflow.py
```

---

## 📜 Official College Identity
**DUM DUM Group of Institution**  
*Excellence in Education, Research & Integrity*  
Institutional Code: `DGD-2026`  
Registrar Office: `registrar@dumdumgroup.edu`  
Administrative Office Hours: Monday - Friday, 9:30 AM to 4:30 PM
