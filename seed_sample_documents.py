"""
Seed script to generate realistic official college policy PDFs for DUM DUM Group of Institution
and ingest them into the Knowledge Base with initial PUBLISHED status.
"""
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from config import SAMPLE_DOCS_DIR, COLLEGE_NAME, COLLEGE_TAGLINE, COLLEGE_CODE
from database import init_db, get_db_connection
from knowledge_base import add_document, publish_document
from auth_service import authenticate


def generate_pdf_doc(filename: str, title: str, sections: list) -> Path:
    """Creates an official looking PDF policy document with institutional branding."""
    file_path = SAMPLE_DOCS_DIR / filename
    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )

    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'Header', parent=styles['Heading1'],
        fontName='Helvetica-Bold', fontSize=18, leading=22,
        textColor=colors.HexColor('#0d233a'), alignment=1, spaceAfter=4
    )
    sub_header = ParagraphStyle(
        'SubHeader', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=13,
        textColor=colors.HexColor('#4a5568'), alignment=1, spaceAfter=10
    )
    doc_title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=13, leading=17,
        textColor=colors.HexColor('#b45309'), alignment=1, spaceBefore=8, spaceAfter=14
    )
    section_heading = ParagraphStyle(
        'SecHead', parent=styles['Heading3'],
        fontName='Helvetica-Bold', fontSize=11, leading=15,
        textColor=colors.HexColor('#0d233a'), spaceBefore=10, spaceAfter=4
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9.5, leading=14,
        textColor=colors.HexColor('#1f2937'), spaceAfter=8
    )

    story = []
    story.append(Paragraph(f"<b>{COLLEGE_NAME.upper()}</b>", header_style))
    story.append(Paragraph(f"{COLLEGE_TAGLINE} | Code: {COLLEGE_CODE} | Official Regulatory Circular", sub_header))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0d233a'), spaceBefore=2, spaceAfter=10))
    story.append(Paragraph(f"<b>{title.upper()}</b>", doc_title_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceBefore=2, spaceAfter=12))

    for sec_title, sec_content in sections:
        story.append(Paragraph(f"<b>{sec_title}</b>", section_heading))
        story.append(Paragraph(sec_content.replace("\n", "<br/>"), body_style))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#94a3b8'), spaceBefore=10, spaceAfter=5))
    story.append(Paragraph(
        f"Officially ratified by the Academic Council & Registrar of {COLLEGE_NAME}. Published for mandatory compliance.",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7.5, leading=10, alignment=1, textColor=colors.HexColor('#64748b'))
    ))

    doc.build(story)
    return file_path


def seed_all_sample_documents():
    """Generates 4 official documents and seeds them into the SQLite database."""
    init_db()

    # Document 1: Attendance
    doc1_sections = [
        ("Section 1: Mandatory Attendance Requirement",
         "All undergraduate and postgraduate students of DUM DUM Group of Institution must maintain a minimum of 75% attendance in both theory and laboratory courses to qualify for end-semester examinations.\nStudents falling below 75% will be flagged automatically by the biometric tracking system at the end of each instructional month."),
        ("Section 2: Medical Condonation & Exemption Rules",
         "Attendance between 65% and 74% may be condoned on medical grounds by the Dean of Academic Affairs.\nThe student must submit a registered medical practitioner certificate, hospital discharge summary, and fitness certificate to the Department Head within 3 working days of resuming classes.\nNo condonation request will be entertained if submitted after the 3-day deadline."),
        ("Section 3: Detention and Course Repeat",
         "Students with overall attendance below 65% under any circumstances will be strictly detained from appearing in end-semester examinations.\nDetained students are not eligible for compensatory assignments and must repeat the course during subsequent summer or supplementary academic sessions."),
        ("Section 4: Biometric Tracking & Timing",
         "Biometric morning registration opens at 8:30 AM and closes at 9:00 AM at all department kiosk points.\nArrivals recorded between 9:01 AM and 9:15 AM will be marked as late. Accumulating three late entries results in one half-day absence.\nArrivals after 9:15 AM require written permission from the Department Head.")
    ]
    p1 = generate_pdf_doc("Attendance_and_Leave_Regulations_2026.pdf", "Attendance and Leave Regulations 2026", doc1_sections)

    # Document 2: Examinations
    doc2_sections = [
        ("Section 1: Assessment Structure & Evaluation",
         "Academic performance at DUM DUM Group of Institution is evaluated through Continuous Internal Assessment (50%) and End-Semester University Examinations (50%).\nMid-Term Examinations are conducted during the 8th instructional week and contribute 25% to internal assessment scores.\nAssignments, quizzes, and laboratory work comprise the remaining 25%."),
        ("Section 2: Examination Admit Card Eligibility",
         "Admit cards are released 5 working days prior to commencement of examinations via the student portal.\nTo download the admit card, a student must have cleared all pending tuition fees and library books, and achieved minimum 75% attendance.\nEntry into the examination hall is strictly prohibited without a printed admit card and institutional photo ID card."),
        ("Section 3: Grading Scale and Passing Criteria",
         "Evaluation uses a 10-point Relative/Absolute Grading Scale where 'O' (Outstanding) corresponds to Grade Point 10.0, and 'D' (Pass) corresponds to Grade Point 4.0.\nStudents scoring below 40% marks in any subject are awarded grade 'F' (Fail) and must appear for the supplementary examination in the subsequent session."),
        ("Section 4: Re-evaluation and Paper Review Procedure",
         "Students dissatisfied with their evaluation can apply for Answer Script Re-evaluation within 7 calendar days of provisional result publication.\nThe prescribed re-evaluation fee is Rs. 500 per theory subject, payable at the accounts counter or online portal.\nRe-evaluation results verified by an external examiner will be final.")
    ]
    p2 = generate_pdf_doc("Examination_Grading_and_Evaluation_Code_2026.pdf", "Examination, Grading and Evaluation Code 2026", doc2_sections)

    # Document 3: Fees & Hostel
    doc3_sections = [
        ("Section 1: Tuition Fee Payment Timelines & Fines",
         "Semester tuition fees must be cleared by July 10th for the Odd Semester and January 10th for the Even Semester.\nA late fee penalty of Rs. 100 per calendar day is levied for payments made between the 11th and 25th of the fee month.\nStudents failing to pay by the 25th will have their ERP portal access and course registration withheld until cleared."),
        ("Section 2: Institutional Merit-cum-Means Scholarships",
         "DUM DUM Group of Institution awards Merit-cum-Means Scholarships providing up to 50% tuition fee waiver.\nEligibility Criteria: A cumulative CGPA of 8.50 or higher with no backlogs, combined with a verifiable family annual income under Rs. 3,50,000.\nApplications open within the first two weeks of August annually through the Office of Student Welfare."),
        ("Section 3: Hostel Residency Rules & Curfew Timings",
         "The main hostel gates for both boys and girls hostels close strictly at 9:00 PM every evening.\nAll residential students must register their biometric presence with the hostel warden between 8:30 PM and 9:00 PM.\nLeaving campus after 9:00 PM requires an approved Night-Out Pass endorsed by parents and the Chief Warden 24 hours prior."),
        ("Section 4: Dining Hall and Mess Schedule",
         "Hostel mess facilities operate on the following fixed daily schedule:\n- Breakfast: 7:30 AM to 9:00 AM\n- Lunch: 12:30 PM to 2:00 PM\n- Evening Snacks: 5:00 PM to 6:00 PM\n- Dinner: 7:30 PM to 9:30 PM\nOutside food vendors are strictly prohibited past 10:00 PM.")
    ]
    p3 = generate_pdf_doc("Fees_Scholarships_and_Hostel_Manual_2026.pdf", "Fees, Scholarships and Hostel Residence Manual 2026", doc3_sections)

    # Document 4: Bonafide & Services
    doc4_sections = [
        ("Section 1: Bonafide & Study Certificate Guidelines",
         "Bonafide and Study Certificates are issued for official purposes including passport verification, state transport travel concessions, education loan processing, and embassy visa interviews.\nStudents must submit an application specifying the explicit purpose through the student portal.\nStandard issuance turnaround is 2 working days following administrative verification and digital approval by the Registrar."),
        ("Section 2: Central Library Operational Timings",
         "The Central Library operates on the following schedule:\n- Monday to Friday: 8:00 AM to 8:00 PM\n- Saturday: 9:00 AM to 4:00 PM\n- Closed on Sundays and gazetted national holidays.\nDuring examination weeks, reading room hours are extended until 10:00 PM."),
        ("Section 3: Circulation Limits and Overdue Penalties",
         "Undergraduate students are permitted to borrow up to 4 books simultaneously for a duration of 14 calendar days.\nPostgraduate and research scholars may borrow up to 6 books for 21 days.\nAn overdue fine of Rs. 5 per day per book will be charged for unreturned material beyond the due date."),
        ("Section 4: Administrative Office Timings",
         "The Administrative and Accounts Office counters are open Monday through Friday from 9:30 AM to 4:30 PM.\nLunch recess is observed daily from 1:00 PM to 2:00 PM.\nCounters remain closed on second Saturdays and public holidays.")
    ]
    p4 = generate_pdf_doc("Bonafide_and_Student_Services_Handbook_2026.pdf", "Bonafide Certificates and Student Services Handbook 2026", doc4_sections)

    # Ingest and Publish documents under Admin
    admin_user = authenticate("admin", "Admin@123")
    if not admin_user:
        raise RuntimeError("Failed to authenticate admin account during seeding.")

    docs_info = [
        (p1, "Attendance and Leave Regulations 2026"),
        (p2, "Examination, Grading and Evaluation Code 2026"),
        (p3, "Fees, Scholarships and Hostel Residence Manual 2026"),
        (p4, "Bonafide Certificates and Student Services Handbook 2026")
    ]

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        count = cursor.fetchone()[0]

    if count == 0:
        print("Ingesting and publishing official seed documents...")
        for file_path, title in docs_info:
            doc_record = add_document(
                file_path=file_path,
                original_filename=file_path.name,
                title=title,
                uploaded_by_user_id=admin_user["id"],
                uploaded_by_username=admin_user["username"],
                run_ai_analysis=False  # fast deterministic seed
            )
            # Publish as official source
            publish_document(
                document_id=doc_record["id"],
                admin_user=admin_user,
                review_notes="Initial official institutional baseline document published by Registrar."
            )
            print(f"Published: {title} (ID #{doc_record['id']})")
    else:
        print(f"Database already contains {count} documents. Skipping duplicate seeding.")


if __name__ == "__main__":
    seed_all_sample_documents()
