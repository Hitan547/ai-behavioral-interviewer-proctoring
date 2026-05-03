"""
End-to-end debug for recruiter shortlist + n8n invite flow.

What this script does:
1) Generates test PDF resumes (simulates upload)
2) Extracts text from PDF
3) Sends text to LLM matcher
4) Applies shortlist rule
5) Attempts n8n invite send for shortlisted resumes

Run:
    python debug_resume_shortlist_flow.py
"""

from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from matching_service.matcher import score_resume_vs_jd
from recruiter_jd_page import extract_pdf_text, send_invite_via_n8n


JD_TEXT = """
Job Title: Python Backend Developer

Requirements:
- Python
- FastAPI or Django
- SQL (PostgreSQL/SQLite)
- REST API design
- Git version control

Nice to have:
- Docker
- ML deployment
""".strip()


RESUMES = [
    {
        "filename": "test_strong_resume.pdf",
        "content": """
        Hitan Kumar
        hitank2004@gmail.com
        Skills: Python, FastAPI, PostgreSQL, SQLite, Git, REST APIs, Docker
        Experience: Built backend APIs with FastAPI and deployed ML model endpoints.
        """,
    },
    {
        "filename": "test_weak_resume.pdf",
        "content": """
        Alex Writer
        alex.writer@example.com
        Skills: Content writing, social media, MS Word
        Experience: Blog writing and communication support.
        """,
    },
]


def _make_pdf(path: Path, text: str):
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 760
    c.setFont("Helvetica", 12)
    for line in [ln.strip() for ln in text.strip().splitlines() if ln.strip()]:
        c.drawString(50, y, line)
        y -= 18
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = 760
    c.save()


def _is_shortlisted(score: float, name: str, email: str, threshold: float = 7.0) -> bool:
    name_ok = bool((name or "").strip()) and (name or "").strip().lower() != "unknown"
    email_ok = "@" in (email or "") and not (email or "").strip().lower().startswith("unknown@")
    return float(score or 0) >= threshold and name_ok and email_ok


def main():
    root = Path(__file__).resolve().parent
    out_dir = root / "data" / "debug_resumes"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("DEBUG: PDF Upload -> LLM Match -> Shortlist -> n8n Invite")
    print("=" * 78)

    for i, item in enumerate(RESUMES, start=1):
        pdf_path = out_dir / item["filename"]
        _make_pdf(pdf_path, item["content"])

        print(f"\n[{i}] Resume File: {pdf_path.name}")

        file_bytes = pdf_path.read_bytes()
        extracted = extract_pdf_text(file_bytes, pdf_path.name)
        print(f"  - Extracted text length: {len(extracted)}")

        if not extracted.strip():
            print("  - ERROR: PDF text extraction failed")
            continue

        result = score_resume_vs_jd(extracted, JD_TEXT)
        score = result.get("match_score")
        name = result.get("name")
        email = result.get("email")

        print(f"  - LLM score: {score}/10")
        print(f"  - LLM name : {name}")
        print(f"  - LLM email: {email}")
        print(f"  - Reason   : {result.get('match_reason')}")

        shortlisted = _is_shortlisted(score, name, email, threshold=7.0)
        print(f"  - Shortlisted (>=7 + valid identity): {shortlisted}")

        if shortlisted:
            username = (name.split()[0].lower() if name and name != "Unknown" else "candidate") + "1001"
            password = "TempPass123"
            ok, msg = send_invite_via_n8n(
                name=name,
                email=email,
                username=username,
                password=password,
                job_title="Python Backend Developer",
                deadline="30 Apr 2026",
            )
            print(f"  - n8n invite result: {ok} | {msg}")

    print("\nDone.")


if __name__ == "__main__":
    main()
