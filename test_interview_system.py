"""
Test Interview System - Comprehensive Validation
=================================================

This script tests all components of the interview system:
1. Database connectivity
2. Groq API configuration
3. Microservices availability
4. Audio/video processing
5. UI rendering

Run this before starting the interview to ensure everything works.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_header(text):
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def print_test(name, passed, message=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {name}")
    if message:
        print(f"     {message}")

def test_environment():
    """Test environment variables"""
    print_header("1. Environment Variables")
    
    # Check Groq API keys
    groq_key = os.getenv("GROQ_API_KEY")
    groq_key_2 = os.getenv("GROQ_API_KEY_2")
    
    print_test("GROQ_API_KEY", bool(groq_key), 
               f"Key: {groq_key[:20]}..." if groq_key else "Not found")
    print_test("GROQ_API_KEY_2", bool(groq_key_2),
               f"Key: {groq_key_2[:20]}..." if groq_key_2 else "Not found")
    
    # Check service URLs
    services = [
        "ANSWER_SERVICE_URL",
        "FUSION_SERVICE_URL",
        "EMOTION_SERVICE_URL",
        "INSIGHT_SERVICE_URL",
        "ENGAGEMENT_SERVICE_URL",
    ]
    
    for service in services:
        url = os.getenv(service)
        print_test(service, bool(url), url or "Not configured")
    
    # Check database
    db_url = os.getenv("DATABASE_URL", "sqlite:///./psysense.db")
    print_test("DATABASE_URL", bool(db_url), db_url)
    
    return bool(groq_key or groq_key_2)

def test_groq_api():
    """Test Groq API connectivity"""
    print_header("2. Groq API Connectivity")
    
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
        
        if not api_key:
            print_test("Groq Client", False, "No API key found")
            return False
        
        client = Groq(api_key=api_key)
        print_test("Groq Client", True, "Client initialized successfully")
        
        # Test with a simple completion (not transcription, to avoid needing audio file)
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "Say 'test'"}],
                max_tokens=10
            )
            print_test("Groq API Call", True, "API is responding")
            return True
        except Exception as e:
            print_test("Groq API Call", False, str(e))
            return False
            
    except ImportError:
        print_test("Groq Package", False, "groq package not installed")
        return False
    except Exception as e:
        print_test("Groq Client", False, str(e))
        return False

def test_database():
    """Test database connectivity"""
    print_header("3. Database")
    
    try:
        from database import init_db, SessionLocal, User
        
        # Initialize database
        init_db()
        print_test("Database Init", True, "Tables created/verified")
        
        # Test query
        db = SessionLocal()
        try:
            user_count = db.query(User).count()
            print_test("Database Query", True, f"{user_count} users in database")
            
            # Check for recruiter account
            recruiter = db.query(User).filter_by(username="recruiter").first()
            print_test("Recruiter Account", bool(recruiter), 
                      "Default recruiter account exists" if recruiter else "Not found")
            
            return True
        finally:
            db.close()
            
    except Exception as e:
        print_test("Database", False, str(e))
        return False

def test_microservices():
    """Test microservice availability"""
    print_header("4. Microservices")
    
    import requests
    
    services = {
        "Answer Service": os.getenv("ANSWER_SERVICE_URL", "http://localhost:8000"),
        "Fusion Service": os.getenv("FUSION_SERVICE_URL", "http://localhost:8001"),
        "Emotion Service": os.getenv("EMOTION_SERVICE_URL", "http://localhost:8002"),
        "Insight Service": os.getenv("INSIGHT_SERVICE_URL", "http://localhost:8003"),
        "Engagement Service": os.getenv("ENGAGEMENT_SERVICE_URL", "http://localhost:8004"),
    }
    
    all_ok = True
    for name, url in services.items():
        try:
            ok = False
            hit = ""

            # Support both common health endpoints used in this repo.
            for path in ("/health", "/"):
                probe = requests.get(f"{url}{path}", timeout=2)
                if probe.status_code == 200:
                    ok = True
                    hit = path
                    break

            print_test(name, ok, f"{url}{hit or '/health,/'}")
            if not ok:
                all_ok = False
        except requests.exceptions.ConnectionError:
            print_test(name, False, f"{url} - Not running")
            all_ok = False
        except Exception as e:
            print_test(name, False, f"{url} - {str(e)}")
            all_ok = False
    
    return all_ok

def test_audio_processing():
    """Test audio processing modules"""
    print_header("5. Audio Processing")
    
    try:
        import numpy as np
        print_test("NumPy", True, f"Version {np.__version__}")
    except ImportError:
        print_test("NumPy", False, "Not installed")
        return False
    
    try:
        import scipy
        print_test("SciPy", True, f"Version {scipy.__version__}")
    except ImportError:
        print_test("SciPy", False, "Not installed - audio resampling will use fallback")
    
    try:
        from audio_capture_robust import save_audio_frames_to_wav, transcribe_wav
        print_test("Audio Capture Module", True, "Imported successfully")
    except Exception as e:
        print_test("Audio Capture Module", False, str(e))
        return False
    
    try:
        from whisper_audio import _transcribe_with_groq
        print_test("Whisper Module", True, "Imported successfully")
    except Exception as e:
        print_test("Whisper Module", False, str(e))
        return False
    
    return True

def test_video_processing():
    """Test video processing modules"""
    print_header("6. Video Processing")
    
    try:
        import cv2
        print_test("OpenCV", True, f"Version {cv2.__version__}")
    except ImportError:
        print_test("OpenCV", False, "Not installed")
        return False
    
    try:
        from engagement_realtime import EngagementDetector
        print_test("Engagement Detector", True, "Imported successfully")
    except Exception as e:
        print_test("Engagement Detector", False, str(e))
        return False
    
    return True

def test_streamlit_webrtc():
    """Test Streamlit WebRTC"""
    print_header("7. Streamlit WebRTC")
    
    try:
        import streamlit_webrtc
        print_test("streamlit-webrtc", True, f"Version {streamlit_webrtc.__version__}")
    except ImportError:
        print_test("streamlit-webrtc", False, "Not installed")
        return False
    except AttributeError:
        print_test("streamlit-webrtc", True, "Installed (version unknown)")
    
    try:
        import av
        print_test("PyAV", True, "Installed")
    except ImportError:
        print_test("PyAV", False, "Not installed")
        return False
    
    return True

def test_ui_dependencies():
    """Test UI dependencies"""
    print_header("8. UI Dependencies")
    
    try:
        import streamlit as st
        print_test("Streamlit", True, f"Version {st.__version__}")
    except ImportError:
        print_test("Streamlit", False, "Not installed")
        return False
    
    try:
        import plotly
        print_test("Plotly", True, f"Version {plotly.__version__}")
    except ImportError:
        print_test("Plotly", False, "Not installed")
        return False
    
    try:
        from reportlab.lib.pagesizes import A4
        print_test("ReportLab", True, "PDF generation available")
    except ImportError:
        print_test("ReportLab", False, "Not installed")
        return False
    
    return True

def run_all_tests():
    """Run all tests"""
    print("\n" + "🔍 PsySense Interview System - Validation Test")
    print("="*60)
    
    results = {
        "Environment": test_environment(),
        "Groq API": test_groq_api(),
        "Database": test_database(),
        "Microservices": test_microservices(),
        "Audio Processing": test_audio_processing(),
        "Video Processing": test_video_processing(),
        "Streamlit WebRTC": test_streamlit_webrtc(),
        "UI Dependencies": test_ui_dependencies(),
    }
    
    print_header("Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All systems operational! Ready to start interview.")
        return 0
    else:
        print("\n⚠️ Some systems failed. Please fix the issues above before starting.")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
