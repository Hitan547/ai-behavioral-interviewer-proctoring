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
    answers_by_index = {
        int(answer.get("questionIndex", -1)): answer
        for answer in submission.get("answers", [])
        if isinstance(answer, dict)
    }
    lines = [
        "Talentryx AI Candidate Assessment Report",
        "",
        f"Candidate: {candidate.get('name', candidate.get('candidateId', 'Candidate'))}",
        f"Email: {candidate.get('email', '')}",
        f"Job: {job.get('title', job.get('jobId', 'Job'))}",
        f"Answer Score Before Integrity Penalty: {result.get('baseScore', result.get('finalScore', 0))}/100",
        f"Final Score: {result.get('finalScore', 0)}/100",
        f"Assessment Status: {result.get('assessmentStatus', 'Below Threshold')}",
        f"Recommendation: {result.get('recommendation', 'Needs Review')}",
        f"Minimum Pass Score: {result.get('minPassScore', job.get('minPassScore', 60))}/100",
        f"Submission: {submission.get('submissionId', '')}",
        "",
        "Integrity & Proctoring Summary",
    ]
    integrity = result.get("integrityRisk", {}) if isinstance(result.get("integrityRisk"), dict) else {}
    lines.extend([
        f"Risk Level: {integrity.get('level', 'Low')} (Penalty: -{integrity.get('scorePenalty', 0)} pts)",
        f"Tab Switches: {integrity.get('tabSwitches', 0)}",
        f"Fullscreen Exits: {integrity.get('fullscreenExits', 0)}",
        f"Copy/Paste Attempts: {integrity.get('copyPasteAttempts', 0)}",
        f"DevTools Attempts: {integrity.get('devtoolsAttempts', 0)}",
        f"Face Not Detected: {integrity.get('faceNotDetected', 0)}",
        f"Multiple Faces: {integrity.get('multipleFaces', 0)}",
        "",
        "Question Breakdown",
    ])
    if result.get("assessmentStatus") == "Review Required":
        lines.extend([
            "Review Required: Answer score meets the role threshold, but proctoring risk",
            "requires recruiter review before making a hiring decision.",
            "",
        ])

    for item in result.get("perQuestion", [])[:10]:
        if not isinstance(item, dict):
            continue
        method = item.get("method", "unknown")
        verdict = item.get("recruiterVerdict") or item.get("verdict", "")
        question_index = int(item.get("questionIndex", 0))
        answer_text = str(answers_by_index.get(question_index, {}).get("answerText", "")).strip()
        lines.extend([
            f"Q{question_index + 1}: {item.get('score', 0)}/100 - {verdict} ({method})",
            _wrap(f"Question: {item.get('question', '')}", 92),
            _wrap(f"Answer: {answer_text or 'No answer recorded.'}", 92),
            _wrap(f"Summary: {item.get('summary', '')}", 92),
        ])
        # Include LLM dimensions if available
        dims = item.get("dimensions")
        if isinstance(dims, dict):
            dim_parts = [f"{k}:{v}" for k, v in dims.items()]
            lines.append(f"  Dimensions: {', '.join(dim_parts)}")
        if item.get("keyStrength") and item["keyStrength"] != "N/A":
            lines.append(f"  Strength: {item['keyStrength']}")
        if item.get("keyImprovement") and item["keyImprovement"] != "N/A":
            lines.append(f"  Improve: {item['keyImprovement']}")
        lines.append("")

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
    pages = _paginate_lines(lines)
    page_refs = " ".join(f"{4 + index * 2} 0 R" for index in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{page_refs}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, page_lines in enumerate(pages):
        page_object_number = 4 + index * 2
        content_object_number = page_object_number + 1
        stream = _page_stream(page_lines)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_object_number} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )

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


def _page_stream(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 9 Tf", "50 770 Td", "12 TL"]
    for line in lines:
        content_lines.append(f"({_escape_pdf_text(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    return "\n".join(content_lines).encode("latin-1", errors="replace")


def _paginate_lines(lines: list[str]) -> list[list[str]]:
    expanded: list[str] = []
    for line in lines:
        expanded.extend(str(line).splitlines() or [""])
    page_size = 58
    return [expanded[index:index + page_size] for index in range(0, len(expanded), page_size)] or [[]]


def _escape_pdf_text(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
