"""
test_matcher.py
---------------
Quick test for matching_service/matcher.py

Run from project root:
    python test_matcher.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from matching_service.matcher import score_resume_vs_jd, score_all_resumes

# ── Dummy Data ────────────────────────────────────────────────────────────

DUMMY_JD = """
Job Title: Python Backend Developer

We are looking for a Python developer with experience in:
- FastAPI or Django REST Framework
- PostgreSQL or SQLite databases
- Machine learning model deployment
- REST API design
- Git and version control

Nice to have:
- Experience with Docker
- Knowledge of NLP or computer vision
- Streamlit or similar dashboard tools

Requirements:
- 1-3 years of experience
- Bachelor's degree in Computer Science or related field
"""

DUMMY_RESUME_STRONG = """
John Smith
john.smith@email.com | LinkedIn: linkedin.com/in/johnsmith

EDUCATION
B.Tech Computer Science — VIT University, 2023

EXPERIENCE
Backend Developer Intern — TechCorp, Jun 2023 – Dec 2023
- Built REST APIs using FastAPI and Python
- Designed SQLite and PostgreSQL database schemas
- Deployed ML models as microservices
- Used Git for version control throughout

PROJECTS
AI Dashboard — Built Streamlit dashboard for data visualization
NLP Classifier — Fine-tuned BERT for sentiment analysis

SKILLS
Python, FastAPI, SQLite, PostgreSQL, Streamlit, Git, Docker, NLP, REST APIs
"""

DUMMY_RESUME_WEAK = """
Rahul Verma
rahul.verma@email.com

EDUCATION
BA English Literature — Mumbai University, 2022

EXPERIENCE
Content Writer — BlogSite, 2022 – 2023
- Wrote articles about technology trends
- Managed social media accounts

SKILLS
MS Word, Google Docs, Content Writing, Social Media
"""

# ── Test 1: Single resume ─────────────────────────────────────────────────

print("=" * 60)
print("TEST 1: Single strong resume vs JD")
print("=" * 60)

result = score_resume_vs_jd(DUMMY_RESUME_STRONG, DUMMY_JD)
print(f"Name:         {result['name']}")
print(f"Email:        {result['email']}")
print(f"Match Score:  {result['match_score']}/10")
print(f"Reason:       {result['match_reason']}")
print(f"Key Matches:  {result['key_matches']}")
print(f"Key Gaps:     {result['key_gaps']}")

# ── Test 2: Batch scoring ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("TEST 2: Batch scoring — 2 resumes ranked")
print("=" * 60)

resumes = [
    {"filename": "john_smith.pdf",  "text": DUMMY_RESUME_STRONG},
    {"filename": "rahul_verma.pdf", "text": DUMMY_RESUME_WEAK},
]

ranked = score_all_resumes(resumes, DUMMY_JD)

for i, r in enumerate(ranked):
    print(f"\nRank #{i+1}: {r['name']} ({r['filename']})")
    print(f"  Score:  {r['match_score']}/10")
    print(f"  Reason: {r['match_reason']}")
    print(f"  Matches: {r['key_matches']}")
    print(f"  Gaps:    {r['key_gaps']}")

print("\n✅ Test complete.")