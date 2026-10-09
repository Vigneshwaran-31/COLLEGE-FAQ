"""
Document Processor for DUM DUM Group of Institution.
Handles file validation, PDF page-by-page text extraction, OCR for scanned documents and images,
smart semantic chunking, and AI-powered document analysis via Google Gemini.
"""
import os
import re
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
import io

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

from google import genai
from google.genai import types

from config import (
    UPLOADS_DIR,
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_SIZE_MB,
    GEMINI_API_KEY,
    PRIMARY_MODEL,
    FALLBACK_MODELS
)
from audit_service import log_event


class DocumentProcessingError(Exception):
    """Raised when document extraction or validation fails."""
    pass


def validate_file(filename: str, file_bytes: bytes) -> Tuple[bool, str]:
    """
    Validates uploaded file against allowed extensions and size limits.
    """
    if not filename:
        return False, "File must have a valid name."

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type '{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_SIZE_MB:
        return False, f"File size ({size_mb:.2f} MB) exceeds maximum allowed limit of {MAX_UPLOAD_SIZE_MB} MB."

    if len(file_bytes) == 0:
        return False, "Uploaded file is empty (0 bytes)."

    return True, "File is valid."


def sanitize_filename(filename: str) -> str:
    """Sanitizes filename to prevent directory traversal or special character exploits."""
    base = Path(filename).name
    # Keep only alphanumeric, dashes, underscores, and dots
    sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '_', base)
    return sanitized or f"document_{uuid.uuid4().hex[:8]}"


def save_uploaded_file(filename: str, file_bytes: bytes) -> Tuple[Path, str]:
    """
    Saves uploaded file bytes to UPLOADS_DIR with a unique UUID prefix.
    Returns (Path, sanitized_original_filename).
    """
    sanitized_original = sanitize_filename(filename)
    unique_name = f"{uuid.uuid4().hex[:10]}_{sanitized_original}"
    dest_path = UPLOADS_DIR / unique_name
    dest_path.write_bytes(file_bytes)
    return dest_path, sanitized_original


def extract_text_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Extracts text from PDF page by page using PyMuPDF (or pypdf fallback).
    If a page has less than 40 characters, triggers OCR on that page's raster image.
    Returns list of dicts: [{'page_number': 1, 'text': '...', 'is_ocr': False}]
    """
    pages_data: List[Dict[str, Any]] = []

    if PYMUPDF_AVAILABLE:
        doc = fitz.open(str(pdf_path))
        try:
            for page_idx in range(len(doc)):
                page_num = page_idx + 1
                page = doc[page_idx]
                text = page.get_text("text").strip()

                # If text is too sparse, this is likely a scanned document page
                if len(text) < 40:
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    ocr_text = run_ocr_on_image_bytes(img_bytes, f"PDF Page {page_num}")
                    pages_data.append({
                        "page_number": page_num,
                        "text": ocr_text or "[Scanned page without detectable text]",
                        "is_ocr": True
                    })
                else:
                    pages_data.append({
                        "page_number": page_num,
                        "text": text,
                        "is_ocr": False
                    })
        finally:
            doc.close()
    elif PYPDF_AVAILABLE:
        reader = pypdf.PdfReader(str(pdf_path))
        for page_idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            pages_data.append({
                "page_number": page_idx + 1,
                "text": text,
                "is_ocr": False
            })
    else:
        raise DocumentProcessingError("No PDF extraction library available (neither PyMuPDF nor pypdf found).")

    return pages_data


def run_ocr_on_image_bytes(image_bytes: bytes, source_label: str = "Image") -> str:
    """
    Performs OCR on image bytes.
    Uses Gemini Multimodal Vision API if available; falls back to pytesseract if installed.
    """
    # 1. Try Gemini Multimodal Vision OCR first
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models_to_try = [PRIMARY_MODEL] + FALLBACK_MODELS
        for model_name in models_to_try:
            try:
                prompt = (
                    "You are an expert OCR and document analysis engine for DUM DUM Group of Institution. "
                    "Extract and transcribe ALL visible text, tables, headers, signatures, dates, and notices "
                    "from this official document image exactly as written. Do not add outside commentary."
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png")
                    ]
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                # Log warning and try fallback model
                continue

    # 2. Try pytesseract if local Tesseract is available
    if PYTESSERACT_AVAILABLE:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            if text.strip():
                return text.strip()
        except Exception:
            pass

    return f"[{source_label}: Image text could not be extracted via OCR]"


def extract_document_content(file_path: Path) -> List[Dict[str, Any]]:
    """
    Dispatches extraction based on file extension.
    Returns list of page data dicts: [{'page_number': int, 'text': str, 'is_ocr': bool}]
    """
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".png", ".jpg", ".jpeg"):
        file_bytes = file_path.read_bytes()
        extracted_text = run_ocr_on_image_bytes(file_bytes, source_label=file_path.name)
        return [{
            "page_number": 1,
            "text": extracted_text,
            "is_ocr": True
        }]
    else:
        raise DocumentProcessingError(f"Unsupported file format: {ext}")


def chunk_document_pages(
    pages_data: List[Dict[str, Any]],
    target_chunk_words: int = 350,
    overlap_words: int = 50
) -> List[Dict[str, Any]]:
    """
    Chunks document pages semantically.
    Retains page numbers, assigns chunk indices, and infers section headings.
    """
    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for page_item in pages_data:
        page_num = page_item["page_number"]
        page_text = page_item["text"].strip()
        if not page_text:
            continue

        paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in page_text.split("\n") if p.strip()]

        current_words: List[str] = []
        current_heading = None

        for para in paragraphs:
            lines = para.split("\n")
            first_line = lines[0].strip()
            # If first line looks like a header (short, capitalized or numbered)
            if len(first_line) < 80 and (first_line.isupper() or any(first_line.startswith(x) for x in ["Section", "Chapter", "Rule", "1.", "2.", "3.", "Article", "Policy"])):
                current_heading = first_line

            words = para.split()
            if len(current_words) + len(words) > target_chunk_words:
                # Flush current chunk
                content_str = " ".join(current_words).strip()
                if content_str:
                    chunks.append({
                        "chunk_index": chunk_index,
                        "page_number": page_num,
                        "heading": current_heading or f"Page {page_num}",
                        "content": content_str,
                        "token_count": len(current_words)
                    })
                    chunk_index += 1
                # Start new chunk with overlap
                current_words = current_words[-overlap_words:] + words
            else:
                current_words.extend(words)

        # Flush remainder of the page
        if current_words:
            content_str = " ".join(current_words).strip()
            if content_str:
                chunks.append({
                    "chunk_index": chunk_index,
                    "page_number": page_num,
                    "heading": current_heading or f"Page {page_num}",
                    "content": content_str,
                    "token_count": len(current_words)
                })
                chunk_index += 1

    return chunks


def analyze_document_with_gemini(
    full_text: str,
    document_title: str
) -> Dict[str, Any]:
    """
    Uses Gemini to analyze official college document content:
    - Executive Summary
    - Topic tags
    - Key Institutional Rules & Policies
    - Important Dates & Deadlines
    - Relevant Sections

    Includes graceful heuristic fallback if Gemini API is unreachable or rate-limited.
    """
    truncated_text = full_text[:25000]  # Safe token window

    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models_to_try = [PRIMARY_MODEL] + FALLBACK_MODELS

        prompt = f"""
You are an expert Chief Academic & Administrative Analyst for DUM DUM Group of Institution.
Analyze the following official college document titled "{document_title}".

Extract and return your analysis strictly as valid JSON with the following structure:
{{
    "summary": "Clear, comprehensive summary of the document (2-3 paragraphs)",
    "topics": ["List", "of", "official", "topics", "e.g.", "Attendance", "Fees", "Examinations", "Hostel", "Library"],
    "extracted_rules": ["Specific official rule or regulation statement 1", "Specific official rule 2"],
    "important_dates": ["Important schedule, deadline or date 1 with description"],
    "relevant_sections": ["Section Name 1", "Section Name 2"]
}}

Document Content:
\"\"\"{truncated_text}\"\"\"

Return ONLY valid JSON. Do not wrap in markdown quotes if possible.
"""
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    cleaned_json = response.text.strip()
                    # Strip markdown code blocks if present
                    if cleaned_json.startswith("```json"):
                        cleaned_json = cleaned_json[7:]
                    elif cleaned_json.startswith("```"):
                        cleaned_json = cleaned_json[3:]
                    if cleaned_json.endswith("```"):
                        cleaned_json = cleaned_json[:-3]
                    cleaned_json = cleaned_json.strip()

                    parsed = json.loads(cleaned_json)
                    return {
                        "summary": parsed.get("summary", "Official college document summary."),
                        "topics": parsed.get("topics", ["General College Policy"]),
                        "extracted_rules": parsed.get("extracted_rules", []),
                        "important_dates": parsed.get("important_dates", []),
                        "relevant_sections": parsed.get("relevant_sections", []),
                        "analysis_engine": f"Gemini ({model_name})"
                    }
            except Exception:
                continue

    # Heuristic fallback if Gemini API is offline or quota exhausted
    return generate_heuristic_analysis(full_text, document_title)


def generate_heuristic_analysis(full_text: str, document_title: str) -> Dict[str, Any]:
    """Generates structured analysis using rule-based heuristics when LLM is unavailable."""
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # Extract topics
    possible_topics = {
        "Attendance": ["attendance", "75%", "condonation", "medical certificate", "biometric", "absent"],
        "Examinations": ["exam", "examination", "mid-term", "end-sem", "admit card", "grades", "grading"],
        "Fees & Scholarships": ["fee", "tuition", "fine", "scholarship", "dues", "refund"],
        "Library": ["library", "books", "borrow", "circulation", "timings", "reading room"],
        "Hostel & Facilities": ["hostel", "warden", "curfew", "mess", "cafeteria", "room allotment"],
        "Certificates & Services": ["bonafide", "certificate", "character", "transcript", "office hours"]
    }
    found_topics = []
    lower_text = full_text.lower()
    for topic, keywords in possible_topics.items():
        if any(kw in lower_text for kw in keywords):
            found_topics.append(topic)
    if not found_topics:
        found_topics = ["General Institutional Policy"]

    # Extract rules
    extracted_rules = []
    for line in lines:
        if any(w in line.lower() for w in ["must", "mandatory", "required", "shall", "minimum", "forbidden", "fine of"]):
            if 20 < len(line) < 200:
                extracted_rules.append(line)
        if len(extracted_rules) >= 5:
            break

    # Extract dates
    date_patterns = re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\s+\d{4}|\b\d{1,2}/\d{1,2}/\d{4}', full_text)

    summary = (
        f"Official document '{document_title}' issued by DUM DUM Group of Institution. "
        f"This document details regulatory procedures and guidelines pertaining to {', '.join(found_topics)}. "
        f"Total extracted text length is {len(full_text)} characters."
    )

    return {
        "summary": summary,
        "topics": found_topics,
        "extracted_rules": extracted_rules or ["Students must comply with all official institutional guidelines."],
        "important_dates": list(set(date_patterns))[:5],
        "relevant_sections": ["General Provisions", "Regulations", "Administrative Procedure"],
        "analysis_engine": "Heuristic Rule-Based Engine (Fallback)"
    }
