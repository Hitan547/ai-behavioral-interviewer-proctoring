"""Minimal PDF report generator for serverless scoring results."""

from __future__ import annotations

from typing import Any


def generate_report_pdf(
    *,
    job: dict[str, Any],
    candidate: dict[str, Any],
    submission: dict[str, Any],
    result: dict[str, Any],
) -> bytes:
    lines = [
        "PsySense AI Recruiter Report",
        "",
        f"Candidate: {candidate.get('name', candidate.get('candidateId', 'Candidate'))}",
        f"Job: {job.get('title', job.get('jobId', 'Job'))}",
        f"Final Score: {result.get('finalScore', 0)}/100",
        f"Recommendation: {result.get('recommendation', 'Needs Review')}",
        f"Submission: {submission.get('submissionId', '')}",
        "",
        "Integrity Summary",
    ]
    integrity = result.get("integrityRisk", {}) if isinstance(result.get("integrityRisk"), dict) else {}
    lines.extend([
        f"Risk Level: {integrity.get('level', 'Low')}",
        f"Tab Switches: {integrity.get('tabSwitches', 0)}",
        f"Fullscreen Exits: {integrity.get('fullscreenExits', 0)}",
        f"Copy/Paste Attempts: {integrity.get('copyPasteAttempts', 0)}",
        f"DevTools Attempts: {integrity.get('devtoolsAttempts', 0)}",
        "",
        "Question Breakdown",
    ])

    for item in result.get("perQuestion", [])[:10]:
        if not isinstance(item, dict):
            continue
        lines.extend([
            f"Q{int(item.get('questionIndex', 0)) + 1}: {item.get('score', 0)}/100 - {item.get('verdict', '')}",
            _wrap(f"Question: {item.get('question', '')}", 92),
            _wrap(f"Summary: {item.get('summary', '')}", 92),
            "",
        ])

    lines.extend([
        "Decision-Support Notice",
        "This report contains AI-assisted interview analysis for recruiter review.",
        "Scores, recommendations, and integrity signals are not final hiring decisions.",
        "Human reviewers should consider the full application, role requirements,",
        "candidate context, accommodations, and any technical issues.",
    ])

    return _simple_pdf(lines)


def _wrap(text: str, width: int) -> str:
    words = str(text).split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if sum(len(part) + 1 for part in current) + len(word) > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _simple_pdf(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 10 Tf", "50 770 Td", "14 TL"]
    for line in _paginate_lines(lines):
        content_lines.append(f"({_escape_pdf_text(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def _paginate_lines(lines: list[str]) -> list[str]:
    expanded: list[str] = []
    for line in lines:
        expanded.extend(str(line).splitlines() or [""])
    return expanded[:48]


def _escape_pdf_text(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
