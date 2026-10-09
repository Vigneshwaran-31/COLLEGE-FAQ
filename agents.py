"""
CrewAI Agents for DUM DUM Group of Institution College FAQ Assistant.
Configures Question Analysis, Knowledge Base Retrieval, Answer Verification,
and Document Request Drafting agents using Google Gemini.
"""
import os
from typing import Optional
from crewai import Agent, LLM

from config import GEMINI_API_KEY, PRIMARY_MODEL, FALLBACK_MODELS, COLLEGE_NAME
from tools import knowledge_base_search_tool, college_policy_lookup_tool


_cached_llm: Optional[LLM] = None
_active_model_name: str = PRIMARY_MODEL


def get_gemini_llm(force_model: Optional[str] = None) -> LLM:
    """
    Returns configured CrewAI LLM instance backed by Google Gemini.
    Attempts primary model (gemini-2.5-flash), with fallback to gemini-3.5-flash
    if the primary model is deprecated (404) or unavailable.
    """
    global _cached_llm, _active_model_name

    model_name = force_model or _active_model_name or PRIMARY_MODEL
    # Format required by CrewAI: provider/model or gemini/model
    crewai_model_str = f"gemini/{model_name}" if not model_name.startswith("gemini/") else model_name

    return LLM(
        model=crewai_model_str,
        api_key=GEMINI_API_KEY,
        temperature=0.1
    )


def set_active_model(model_name: str):
    """Sets the active Gemini model name."""
    global _active_model_name, _cached_llm
    _active_model_name = model_name
    _cached_llm = None


def get_active_model_name() -> str:
    """Returns the current active model identifier."""
    return _active_model_name


# =====================================================================
# AGENT DEFINITIONS
# =====================================================================

def create_question_analysis_agent(llm: Optional[LLM] = None) -> Agent:
    """Agent responsible for analyzing and breaking down student inquiries."""
    target_llm = llm or get_gemini_llm()
    return Agent(
        role="College FAQ Inquiry Analyst",
        goal=(
            f"Carefully analyze incoming student queries for {COLLEGE_NAME}. "
            "Identify the primary domain (Attendance, Examinations, Fees, Scholarships, Library, "
            "Hostel, Bonafide, Courses, Office Hours), extract key policy terms, and craft exact "
            "retrieval queries for the college records database."
        ),
        backstory=(
            f"You are the Chief Academic Inquiry Specialist at {COLLEGE_NAME}. "
            "You possess an intimate understanding of academic calendars, student regulations, and "
            "institutional terminology. You analyze queries thoroughly so retrieval is pinpoint accurate."
        ),
        llm=target_llm,
        verbose=False,
        allow_delegation=False
    )


def create_retrieval_agent(llm: Optional[LLM] = None) -> Agent:
    """Agent responsible for searching verified published documents."""
    target_llm = llm or get_gemini_llm()
    return Agent(
        role="College Policy Retrieval Specialist",
        goal=(
            f"Search ONLY the official, published knowledge base of {COLLEGE_NAME} "
            "using the Knowledge Base Search Tool and College Policy Lookup Tool. "
            "Retrieve verified text excerpts, precise document titles, and exact page references. "
            "Do NOT make assumptions or retrieve unofficial speculation."
        ),
        backstory=(
            f"You are the Chief Archivist and Records Officer of {COLLEGE_NAME}. "
            "You only trust ratified circulars, published handbooks, and verified administrative notices. "
            "You always cite exact document titles and page numbers."
        ),
        tools=[knowledge_base_search_tool, college_policy_lookup_tool],
        llm=target_llm,
        verbose=False,
        allow_delegation=False
    )


def create_answer_verification_agent(llm: Optional[LLM] = None) -> Agent:
    """Agent responsible for auditing grounding and crafting final student response."""
    target_llm = llm or get_gemini_llm()
    return Agent(
        role="Institutional Verification & Compliance Officer",
        goal=(
            f"Cross-examine the student inquiry against retrieved official excerpts from {COLLEGE_NAME}. "
            "Strict Verification Rule: Every single statement in the answer MUST be directly supported "
            "by the retrieved official document excerpts. "
            "If NO official published records were found, you MUST clearly state: "
            "'According to official records of DUM DUM Group of Institution, this information could not be verified.' "
            "Never invent rules, fabricate dates, or assume policies. Provide clear citations."
        ),
        backstory=(
            f"You are the Senior Compliance and Academic Integrity Auditor of {COLLEGE_NAME}. "
            "Your highest duty is ensuring students receive 100% accurate, legally sound, and verified "
            "institutional answers. You reject any ungrounded assertions."
        ),
        llm=target_llm,
        verbose=False,
        allow_delegation=False
    )


def create_document_drafting_agent(llm: Optional[LLM] = None) -> Agent:
    """Agent responsible for preparing standardized student document drafts."""
    target_llm = llm or get_gemini_llm()
    return Agent(
        role="Official Document Request Drafter",
        goal=(
            f"Draft official student certificates (Bonafide, Study Certificate, Permission Letter, "
            f"Fee Structure) for {COLLEGE_NAME} based strictly on verified student information "
            "and standardized administrative templates. Never fabricate student details, signatures, or seal text."
        ),
        backstory=(
            f"You are the Registrar's Executive Drafting Assistant at {COLLEGE_NAME}. "
            "You compose flawless, formally worded institutional documentation ready for administrative review."
        ),
        llm=target_llm,
        verbose=False,
        allow_delegation=False
    )
