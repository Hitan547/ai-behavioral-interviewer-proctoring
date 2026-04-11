"""
saas_middleware.py
------------------
FastAPI middleware for multi-tenant isolation.
Add to each microservice to enforce org_id scoping.
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from saas_db import get_organization_by_api_key
import os


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Extracts org_id from X-Org-ID header or API key.
    Validates org exists and is active.
    Attaches org_id to request.state for use in endpoints.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        org_id = request.headers.get("X-Org-ID")
        api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        # Resolve org_id
        if not org_id and api_key:
            org = get_organization_by_api_key(api_key)
            if org:
                org_id = org.org_id
        
        if not org_id:
            raise HTTPException(status_code=400, detail="Missing X-Org-ID header or valid API key")
        
        # Validate org exists and is active
        from saas_db import get_organization
        org = get_organization(org_id)
        if not org:
            raise HTTPException(status_code=403, detail="Organization not found")
        if not org.active:
            raise HTTPException(status_code=403, detail="Organization account is inactive")
        
        # Attach to request
        request.state.org_id = org_id
        request.state.org = org
        
        response = await call_next(request)
        return response


def add_tenant_middleware(app):
    """
    Attach TenantMiddleware to a FastAPI app.
    
    Usage in answer_service/main.py:
        from saas_middleware import add_tenant_middleware
        app = FastAPI()
        add_tenant_middleware(app)
    """
    app.add_middleware(TenantMiddleware)


# ── Usage in endpoints ────────────────────────────────────────────────────

"""
Example FastAPI endpoint using org_id isolation:

@app.post("/score-answer")
async def score_answer(request: Request, payload: dict):
    org_id = request.state.org_id  # From middleware
    
    # Only score for this org
    answer = payload['answer']
    question = payload['question']
    jd_text = payload.get('jd_text', '')
    
    # Call Groq
    score = score_cognitive_answer(answer, question, jd_text)
    
    # Save with org_id
    from database import SessionLocal, CandidateSession
    db = SessionLocal()
    try:
        # Filter all queries by org_id
        session = db.query(CandidateSession).filter(
            CandidateSession.id == payload['session_id'],
            CandidateSession.org_id == org_id  # CRITICAL: add this filter
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found in your org")
        
        # Save score...
        db.commit()
    finally:
        db.close()
    
    return {"cognitive_score": score}
"""


# ── Quota enforcement ─────────────────────────────────────────────────────

async def check_quota_before_interview(request: Request):
    """
    FastAPI dependency to check usage quota before allowing an interview.
    
    Usage in endpoint:
        @app.post("/start-interview", dependencies=[Depends(check_quota_before_interview)])
        async def start_interview(request: Request):
            ...
    """
    from saas_db import check_usage_quota, is_trial_expired
    
    org_id = request.state.org_id
    
    allowed, message, used, limit = check_usage_quota(org_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=message)
    
    return org_id


async def log_interview_usage(org_id: str):
    """
    Call this after save_session() to increment interview counter.
    """
    from saas_db import increment_interview_count, reset_monthly_quota
    
    reset_monthly_quota(org_id)  # Reset if new month
    increment_interview_count(org_id)