@echo off
echo Starting PsySense AI System...
cd /d %~dp0

echo Starting Streamlit UI first...
start cmd /k streamlit run demo_app.py

echo Waiting for Streamlit to load mediapipe...
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
