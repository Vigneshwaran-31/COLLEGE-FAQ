"""
Tests for document processing, PDF extraction, image OCR handling, chunking, and AI analysis.
"""
from pathlib import Path
from PIL import Image
import io

from document_processor import (
    validate_file,
    sanitize_filename,
    chunk_document_pages,
    extract_text_from_pdf,
    run_ocr_on_image_bytes,
    generate_heuristic_analysis
)


def test_validate_file_extensions_and_sizes():
    # Valid PDF
    valid, msg = validate_file("notice.pdf", b"%PDF-1.4 sample content")
    assert valid is True

    # Valid PNG
    valid, msg = validate_file("campus_map.png", b"\x89PNG\r\n\x1a\nfakeimage")
    assert valid is True

    # Disallowed extension
    invalid, msg = validate_file("malicious.exe", b"MZexecutable")
    assert invalid is False
    assert "Unsupported file type" in msg

    # Empty file
    invalid_empty, msg = validate_file("empty.pdf", b"")
    assert invalid_empty is False
    assert "empty" in msg

    # File exceeding size limit (16MB > 15MB limit)
    large_bytes = b"0" * (16 * 1024 * 1024)
    invalid_size, msg = validate_file("large.pdf", large_bytes)
    assert invalid_size is False
    assert "exceeds maximum allowed limit" in msg


def test_sanitize_filename():
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("rule*#book?.pdf") == "rule__book_.pdf"
    assert sanitize_filename("attendance_2026.pdf") == "attendance_2026.pdf"


def test_chunk_document_pages():
    sample_pages = [
        {
            "page_number": 1,
            "text": "Rule 1: Attendance\nStudents must attend 75% of classes.\n\nSection 2: Medical Leave\nLeave is allowed with certificate."
        },
        {
            "page_number": 2,
            "text": "Chapter 3: Examinations\nMid-terms are conducted in the 8th week of the academic term."
        }
    ]
    chunks = chunk_document_pages(sample_pages, target_chunk_words=20, overlap_words=5)
    assert len(chunks) >= 2
    for ch in chunks:
        assert "chunk_index" in ch
        assert "page_number" in ch
        assert "content" in ch
        assert ch["token_count"] > 0


def test_image_ocr_handling():
    # Create simple blank image in memory
    img = Image.new('RGB', (100, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()

    result = run_ocr_on_image_bytes(img_bytes, source_label="Test Image")
    assert isinstance(result, str)
    assert len(result) > 0


def test_heuristic_analysis_fallback():
    sample_text = (
        "DUM DUM Group of Institution Official Notice.\n"
        "All students must maintain 75% attendance to sit for examinations.\n"
        "Late fee fine of Rs. 100 per day after July 10, 2026.\n"
        "Hostel gates close at 9:00 PM."
    )
    analysis = generate_heuristic_analysis(sample_text, "Official Notice 2026")
    assert "Attendance" in analysis["topics"] or "Fees & Scholarships" in analysis["topics"]
    assert len(analysis["extracted_rules"]) > 0
    assert "Official document" in analysis["summary"]
