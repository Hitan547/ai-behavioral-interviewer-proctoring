@echo off
echo Starting PsySense AI System...
cd /d %~dp0

:: ── Environment variables ──
set ANSWER_SERVICE_URL=http://127.0.0.1:8000
set FUSION_SERVICE_URL=http://127.0.0.1:8001
set EMOTION_SERVICE_URL=http://127.0.0.1:8002
set INSIGHT_SERVICE_URL=http://127.0.0.1:8003
set ENGAGEMENT_SERVICE_URL=http://127.0.0.1:8004
set N8N_RESULT_WEBHOOK=http://localhost:5678/webhook/psysense-interview
set N8N_INVITE_WEBHOOK=http://localhost:5678/webhook/candidate-invite
set APP_BASE_URL=http://localhost:8501
set GROQ_API_KEY=paste_your_actual_key_here
set GROQ_API_KEY_2=paste_your_actual_second_key_here
set DATABASE_URL=sqlite:///data/psysense.db
set RECRUITER_DEFAULT_PASSWORD=ChooseAStrongPasswordHere2024!
set STRIPE_API_KEY=sk_test_your_real_key_here
set STRIPE_PRICE_STARTER=price_your_starter_price_id
set STRIPE_PRICE_PRO=price_your_pro_price_id
:: ── Start services ──
echo Starting Streamlit UI first...
start cmd /k streamlit run demo_app.py

echo Waiting for Streamlit to load...
timeout /t 8

echo Starting Answer Service...
start cmd /k uvicorn answer_service.main:app --port 8000

echo Starting Fusion Service...
start cmd /k uvicorn fusion_service.main:app --port 8001

echo Starting Emotion Service...
start cmd /k uvicorn emotion_service.main:app --port 8002

echo Starting Insight Service...
start cmd /k uvicorn insight_service.main:app --port 8003

echo Starting Engagement Service...
start cmd /k uvicorn engagement_service.main:app --port 8004

echo All services started.
pause