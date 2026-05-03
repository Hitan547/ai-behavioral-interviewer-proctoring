@echo off
REM ============================================================================
REM PsySense Interview System - Complete Startup Script
REM ============================================================================
REM This script:
REM 1. Validates the environment
REM 2. Tests all dependencies
REM 3. Starts all microservices
REM 4. Launches the main application
REM ============================================================================

echo.
echo ========================================
echo   PsySense Interview System
echo   Complete Startup Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/6] Python detected
python --version

REM Check if virtual environment exists
if not exist "venv310\Scripts\activate.bat" (
    echo.
    echo [WARNING] Virtual environment not found
    echo Creating virtual environment...
    python -m venv venv310
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created
)

REM Activate virtual environment
echo.
echo [2/6] Activating virtual environment...
call venv310\Scripts\activate.bat

REM Install/update dependencies
echo.
echo [3/6] Checking dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [SUCCESS] Dependencies installed

REM Run validation tests
echo.
echo [4/6] Running system validation tests...
python test_interview_system.py
if errorlevel 1 (
    echo.
    echo [WARNING] Some tests failed
    echo The system may not work correctly
    echo.
    choice /C YN /M "Do you want to continue anyway"
    if errorlevel 2 exit /b 1
)

REM Start microservices
echo.
echo [5/6] Starting microservices...
echo.

REM Check if services are already running
tasklist /FI "WINDOWTITLE eq Answer Service*" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [INFO] Services appear to be already running
    choice /C YN /M "Kill existing services and restart"
    if not errorlevel 2 (
        echo Stopping existing services...
        taskkill /F /FI "WINDOWTITLE eq *Service*" >nul 2>&1
        timeout /t 2 >nul
    )
)

echo Starting Answer Service (port 8000)...
start "Answer Service" cmd /k "cd answer_service && python main.py"
timeout /t 2 >nul

echo Starting Fusion Service (port 8001)...
start "Fusion Service" cmd /k "cd fusion_service && python main.py"
timeout /t 2 >nul

echo Starting Emotion Service (port 8002)...
start "Emotion Service" cmd /k "cd emotion_service && python main.py"
timeout /t 2 >nul

echo Starting Insight Service (port 8003)...
start "Insight Service" cmd /k "cd insight_service && python main.py"
timeout /t 2 >nul

echo Starting Engagement Service (port 8004)...
start "Engagement Service" cmd /k "cd engagement_service && python main.py"
timeout /t 2 >nul

echo.
echo [SUCCESS] All microservices started
echo Waiting for services to initialize...
timeout /t 5 >nul

REM Start main application
echo.
echo [6/6] Starting main application...
echo.
echo ========================================
echo   Application will open in browser
echo   URL: http://localhost:8501
echo ========================================
echo.
echo Press Ctrl+C to stop the application
echo.

streamlit run demo_app.py --server.port 8501 --server.headless true

REM Cleanup on exit
echo.
echo Shutting down services...
taskkill /F /FI "WINDOWTITLE eq *Service*" >nul 2>&1

echo.
echo ========================================
echo   Application stopped
echo ========================================
pause
