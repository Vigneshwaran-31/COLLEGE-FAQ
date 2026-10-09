"""
CrewAI Tasks for DUM DUM Group of Institution College FAQ Workflows.
Defines explicit tasks for question analysis, verified retrieval, compliance verification,
and document request drafting.
"""
from typing import Dict, Any, Optional
from crewai import Task, Agent


def create_analysis_task(agent: Agent, question: str) -> Task:
    """Task to analyze student inquiry and generate search strategy."""
    return Task(
        description=(
            f"Analyze the following student inquiry for DUM DUM Group of Institution:\n"
            f"Query: \"{question}\"\n\n"
            "Instructions:\n"
            "1. Identify the primary institutional domain (e.g. Attendance, Examinations, Fees, Scholarships, "
            "Library, Hostel, Bonafide Certificates, Office Timings, Academic Policies).\n"
            "2. Extract the key terms, constraints, and policy concepts.\n"
            "3. Formulate the best search query to find the official circular or regulation in the published knowledge base."
        ),
        expected_output=(
            "A concise analysis specifying the category, key terms, and the exact knowledge-base search query."
        ),
        agent=agent
    )


def create_retrieval_task(agent: Agent, question: str, context_tasks: Optional[list] = None) -> Task:
    """Task to search official published documents using knowledge base retrieval tools."""
    return Task(
        description=(
            f"Using the analysis from the previous step and the student question: \"{question}\", "
            "search the published knowledge base using the Knowledge Base Search Tool or College Policy Topic Lookup Tool.\n\n"
            "Requirements:\n"
            "- Only retrieve and report information from PUBLISHED official documents.\n"
            "- Extract the exact document titles, page numbers, and relevant policy sentences.\n"
            "- If the search yields no published records or only irrelevant information, explicitly report 'NO_OFFICIAL_RECORDS_FOUND'."
        ),
        expected_output=(
            "Extracted official excerpts with document names and page references, OR explicit confirmation that no published record exists."
        ),
        agent=agent,
        context=context_tasks or []
    )


def create_verification_and_answer_task(agent: Agent, question: str, context_tasks: Optional[list] = None) -> Task:
    """Task to verify factual grounding and format student-facing answer."""
    return Task(
        description=(
            f"Review the student question: \"{question}\" and the retrieved official documents from earlier tasks.\n\n"
            "STRICT GROUNDING INSTRUCTIONS:\n"
            "1. If official document excerpts WERE FOUND:\n"
            "   - Provide a clear, polite, and helpful answer grounded entirely in the official text.\n"
            "   - Clearly list the official sources with exact Document Title and Page Reference.\n"
            "   - Mark Verification Status as: VERIFIED_OFFICIAL.\n\n"
            "2. If NO official published records were found (or information is incomplete):\n"
            "   - State clearly: 'According to official college records of DUM DUM Group of Institution, this information could not be verified.'\n"
            "   - Advise the student to contact the Administrative Office or relevant Department Head.\n"
            "   - NEVER make up or assume any college rule, date, fee amount, or policy.\n"
            "   - Mark Verification Status as: UNVERIFIED.\n\n"
            "Format your final response in clear Markdown with an Answer section, Sources section, and Verification Status badge."
        ),
        expected_output=(
            "A structured answer containing: grounded explanation, sources with page references (or statement of unverified status), "
            "and verification status (VERIFIED_OFFICIAL or UNVERIFIED)."
        ),
        agent=agent,
        context=context_tasks or []
    )


def create_document_draft_task(agent: Agent, request_data: Dict[str, Any]) -> Task:
    """Task to draft formal certificate or letter for administrative approval."""
    doc_type = request_data.get("doc_type", "BONAFIDE")
    student_name = request_data.get("student_name", "Student")
    roll_number = request_data.get("roll_number", "N/A")
    department = request_data.get("department", "Academics")
    year_sem = request_data.get("year_semester", "Current")
    purpose = request_data.get("purpose", "Official requirement")
    notes = request_data.get("supporting_notes", "")

    return Task(
        description=(
            f"Prepare a formal institutional draft certificate for DUM DUM Group of Institution.\n"
            f"Details:\n"
            f"- Document Type: {doc_type}\n"
            f"- Student Name: {student_name}\n"
            f"- Roll / Registration No: {roll_number}\n"
            f"- Department: {department}\n"
            f"- Year/Semester: {year_sem}\n"
            f"- Purpose: {purpose}\n"
            f"- Additional Notes: {notes}\n\n"
            "Guidelines:\n"
            "- Adhere strictly to formal academic certification wording.\n"
            "- Do not fabricate signatures, stamps, or unverified claims.\n"
            "- End the draft with: '[Draft Prepared for Administrative Review - Requires Registrar Approval]'"
        ),
        expected_output=(
            "Complete draft certificate body text with institutional header, student details, formal certification clause, and approval placeholder."
        ),
        agent=agent
    )
