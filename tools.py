"""
CrewAI Retrieval and Policy Tools for DUM DUM Group of Institution.
Interacts with the verified SQLite Knowledge Base to retrieve grounded official documents.
"""
from typing import Type, List, Dict, Any
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from knowledge_base import search_published_knowledge_base, get_all_documents


class KnowledgeBaseSearchInput(BaseModel):
    query: str = Field(..., description="The student FAQ inquiry or search phrase to look up in official published college documents.")


class KnowledgeBaseSearchTool(BaseTool):
    name: str = "knowledge_base_search"
    description: str = (
        "Searches ONLY official, verified, and published college policy documents for DUM DUM Group of Institution. "
        "Returns grounded excerpts along with document titles and page references. "
        "If no official published document matches, returns an empty result."
    )
    args_schema: Type[BaseModel] = KnowledgeBaseSearchInput

    def _run(self, query: str) -> str:
        results = search_published_knowledge_base(query=query, top_k=4)
        if not results:
            return (
                "NO_OFFICIAL_RECORDS_FOUND: No approved and published institutional document matches "
                f"the query: '{query}'. The official knowledge base does not contain verified guidelines for this topic."
            )

        formatted_output = [f"FOUND {len(results)} OFFICIAL VERIFIED EXCERPT(S):\n"]
        for idx, item in enumerate(results, start=1):
            formatted_output.append(
                f"--- [SOURCE {idx}] ---\n"
                f"Document Title: {item['document_title']}\n"
                f"Original Filename: {item['original_filename']}\n"
                f"Page Reference: Page {item['page_number']}\n"
                f"Section/Heading: {item['heading']}\n"
                f"Verification Status: OFFICIAL_PUBLISHED_RECORD\n"
                f"Excerpt Content:\n{item['content']}\n"
            )
        return "\n".join(formatted_output)


class CollegePolicyTopicInput(BaseModel):
    topic_name: str = Field(..., description="Topic name e.g. Attendance, Examinations, Fees, Library, Hostel, Bonafide")


class CollegePolicyLookupTool(BaseTool):
    name: str = "college_policy_topic_lookup"
    description: str = (
        "Retrieves summarized official rules and policies by institutional domain "
        "(Attendance, Examinations, Fees, Library, Hostel, Bonafide) from published documents."
    )
    args_schema: Type[BaseModel] = CollegePolicyTopicInput

    def _run(self, topic_name: str) -> str:
        clean_topic = topic_name.strip().lower()
        published_docs = [d for d in get_all_documents() if d.get("status") == "PUBLISHED"]

        matching_rules = []
        for doc in published_docs:
            topics = [t.lower() for t in doc.get("topics_list", [])]
            if clean_topic in topics or any(clean_topic in t for t in topics) or clean_topic in doc.get("title", "").lower():
                rules = doc.get("rules_list", [])
                if rules:
                    matching_rules.append(
                        f"Document: {doc['title']} (Published)\nRules:\n- " + "\n- ".join(rules)
                    )

        if not matching_rules:
            return f"No official published rules found specifically categorized under topic '{topic_name}'."

        return "\n\n".join(matching_rules)


knowledge_base_search_tool = KnowledgeBaseSearchTool()
college_policy_lookup_tool = CollegePolicyLookupTool()
