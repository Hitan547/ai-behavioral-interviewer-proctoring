@echo off
echo Starting PsySense AI System...
cd /d %~dp0
set "PY_EXE=%~dp0venv310\Scripts\python.exe"

if not exist "%PY_EXE%" (
	echo ERROR: Python venv not found at %PY_EXE%
	pause
	exit /b 1
)

:: ── Environment variables ──
set ANSWER_SERVICE_URL=http://127.0.0.1:8000
set FUSION_SERVICE_URL=http://127.0.0.1:8001
set EMOTION_SERVICE_URL=http://127.0.0.1:8002
set INSIGHT_SERVICE_URL=http://127.0.0.1:8003
set ENGAGEMENT_SERVICE_URL=http://127.0.0.1:8004
set N8N_RESULT_WEBHOOK=http://localhost:5678/webhook/psysense-interview
set N8N_INVITE_WEBHOOK=https://hitan2004.app.n8n.cloud/webhook/candidate-invite
set APP_BASE_URL=http://localhost:8501
:: Do not set GROQ keys here. Keep them in .env to avoid blank env overrides.
set DATABASE_URL=sqlite:///./psysense.db
set RECRUITER_DEFAULT_PASSWORD=ChooseAStrongPasswordHere2024!
set STRIPE_API_KEY=sk_test_your_real_key_here
set STRIPE_PRICE_STARTER=price_your_starter_price_id
set STRIPE_PRICE_PRO=price_your_pro_price_id
:: ── Start services ──
echo Starting Streamlit UI first...
start cmd /k ""%PY_EXE%" -m streamlit run demo_app.py"

echo Waiting for Streamlit to load...
timeout /t 8

echo Starting Answer Service...
start cmd /k ""%PY_EXE%" -m uvicorn answer_service.main:app --port 8000"

echo Starting Fusion Service...
start cmd /k ""%PY_EXE%" -m uvicorn fusion_service.main:app --port 8001"

echo Starting Emotion Service...
start cmd /k ""%PY_EXE%" -m uvicorn emotion_service.main:app --port 8002"

echo Starting Insight Service...
start cmd /k ""%PY_EXE%" -m uvicorn insight_service.main:app --port 8003"

echo Starting Engagement Service...
start cmd /k ""%PY_EXE%" -m uvicorn engagement_service.main:app --port 8004"

echo All services started.
pause
