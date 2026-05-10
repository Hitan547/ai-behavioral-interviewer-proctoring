"""Resume text extraction for serverless interview preparation."""

from __future__ import annotations

import os
import tempfile


def extract_resume_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from a PDF resume.

    The Lambda package should include a PDF parser before production deployment.
    Tests can inject this function, and local fallback keeps failures explicit.
    """
    if not pdf_bytes:
        raise ValueError("Uploaded resume is empty.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        text = _extract_with_pypdf(tmp_path)
        if len(text.strip()) < 50:
            raise ValueError("Could not extract enough text from resume PDF.")
        return text.strip()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _extract_with_pypdf(pdf_path: str) -> str:
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyPDF2 must be packaged with the resume preparation Lambda.") from exc

    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)
