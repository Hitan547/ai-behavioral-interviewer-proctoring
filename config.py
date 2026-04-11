# config.py
import os
from dotenv import load_dotenv

load_dotenv()

APP_BASE_URL           = os.getenv("APP_BASE_URL",           "http://localhost:8501")
ANSWER_SERVICE_URL     = os.getenv("ANSWER_SERVICE_URL",     "http://127.0.0.1:8000")
FUSION_SERVICE_URL     = os.getenv("FUSION_SERVICE_URL",     "http://127.0.0.1:8001")
EMOTION_SERVICE_URL    = os.getenv("EMOTION_SERVICE_URL",    "http://127.0.0.1:8002")
INSIGHT_SERVICE_URL    = os.getenv("INSIGHT_SERVICE_URL",    "http://127.0.0.1:8003")
ENGAGEMENT_SERVICE_URL = os.getenv("ENGAGEMENT_SERVICE_URL", "http://127.0.0.1:8004")
GROQ_API_KEY           = os.getenv("GROQ_API_KEY")
GROQ_API_KEY_2         = os.getenv("GROQ_API_KEY_2")
N8N_RESULT_WEBHOOK     = os.getenv("N8N_RESULT_WEBHOOK",     "http://localhost:5678/webhook/psysense-interview")
N8N_INVITE_WEBHOOK     = os.getenv("N8N_INVITE_WEBHOOK",     "http://localhost:5678/webhook/candidate-invite")
RECRUITER_DEFAULT_PASSWORD = os.getenv("RECRUITER_DEFAULT_PASSWORD", "admin123")
DATABASE_URL           = os.getenv("DATABASE_URL",           "sqlite:///data/psysense.db")