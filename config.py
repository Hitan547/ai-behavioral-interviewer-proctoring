# config.py
import os
from dotenv import load_dotenv

load_dotenv()

ENVIRONMENT            = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION          = ENVIRONMENT in {"prod", "production"}
APP_BASE_URL           = os.getenv("APP_BASE_URL",           "http://localhost:8501")
ANSWER_SERVICE_URL     = os.getenv("ANSWER_SERVICE_URL",     "http://127.0.0.1:8000")
FUSION_SERVICE_URL     = os.getenv("FUSION_SERVICE_URL",     "http://127.0.0.1:8001")
EMOTION_SERVICE_URL    = os.getenv("EMOTION_SERVICE_URL",    "http://127.0.0.1:8002")
INSIGHT_SERVICE_URL    = os.getenv("INSIGHT_SERVICE_URL",    "http://127.0.0.1:8003")
ENGAGEMENT_SERVICE_URL = os.getenv("ENGAGEMENT_SERVICE_URL", "http://127.0.0.1:8004")
GROQ_API_KEY           = os.getenv("GROQ_API_KEY")
GROQ_API_KEY_2         = os.getenv("GROQ_API_KEY_2")
ENABLE_CUSTOM_EMOTION_MODEL = os.getenv("ENABLE_CUSTOM_EMOTION_MODEL", "0").strip()
N8N_RESULT_WEBHOOK     = os.getenv("N8N_RESULT_WEBHOOK",     "http://localhost:5678/webhook/psysense-interview")
N8N_INVITE_WEBHOOK     = os.getenv("N8N_INVITE_WEBHOOK",     "https://hitan2004.app.n8n.cloud/webhook/candidate-invite")
RECRUITER_DEFAULT_PASSWORD = os.getenv("RECRUITER_DEFAULT_PASSWORD", "admin123")
DATABASE_URL           = os.getenv("DATABASE_URL",           "sqlite:///./psysense.db")
DATABASE_POOL_SIZE     = int(os.getenv("DATABASE_POOL_SIZE",  "5"))
DATABASE_MAX_OVERFLOW  = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
SENTRY_DSN             = os.getenv("SENTRY_DSN",             "")


def _is_local_url(value: str) -> bool:
    value = (value or "").lower()
    return "localhost" in value or "127.0.0.1" in value


def deployment_config_errors() -> list[str]:
    """Return production-only config problems with clear fix messages."""
    if not IS_PRODUCTION:
        return []

    errors = []
    if not (GROQ_API_KEY or GROQ_API_KEY_2):
        errors.append("Set GROQ_API_KEY or GROQ_API_KEY_2 in the AWS environment.")
    if _is_local_url(APP_BASE_URL) or not APP_BASE_URL.startswith("https://"):
        errors.append("Set APP_BASE_URL to the public HTTPS application URL.")
    if DATABASE_URL.startswith("sqlite") and os.getenv("ALLOW_SQLITE_IN_PRODUCTION") != "1":
        errors.append("Set DATABASE_URL to AWS RDS Postgres, not SQLite.")
    if RECRUITER_DEFAULT_PASSWORD == "admin123":
        errors.append("Set a strong RECRUITER_DEFAULT_PASSWORD.")
    if _is_local_url(N8N_RESULT_WEBHOOK):
        errors.append("Set N8N_RESULT_WEBHOOK to the production n8n webhook URL.")
    if _is_local_url(N8N_INVITE_WEBHOOK):
        errors.append("Set N8N_INVITE_WEBHOOK to the production n8n webhook URL.")
    return errors


_deployment_errors = deployment_config_errors()
if _deployment_errors and os.getenv("STRICT_DEPLOYMENT_CONFIG", "1") != "0":
    raise RuntimeError(
        "Production deployment configuration is incomplete:\n- "
        + "\n- ".join(_deployment_errors)
    )
