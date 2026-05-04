# Quick Reference Card - Interview System

## 🚀 Quick Start (30 seconds)

```bash
# Option 1: Complete startup (recommended)
START_INTERVIEW_SYSTEM.bat

# Option 2: Original script
run_system.bat

# Option 3: Manual
venv310\Scripts\activate
streamlit run demo_app.py
```

## 🔑 Default Credentials

**Recruiter:**
- Username: `recruiter`
- Password: `admin123`

**Student:**
- Create account on login page
- Or use existing credentials

## 📋 Quick Troubleshooting

| Problem | Quick Fix |
|---------|-----------|
| Camera not starting | Close Zoom/Teams → Click "Reset Camera" |
| No speech detected | Check Windows Sound Settings → Test in Voice Recorder |
| Transcription failed | Check internet → Verify API key in `.env` |
| Services not starting | Run `taskkill /F /IM python.exe` → Restart |
| Browser permission denied | Click camera icon in address bar → Reset permissions |

## 🧪 Quick Test (2 minutes)

```bash
# 1. Validate system
python test_interview_system.py

# 2. Start application
START_INTERVIEW_SYSTEM.bat

# 3. Test interview
# - Login as student
# - Upload resume
# - Camera Check → Click START
# - Record one answer
# - Verify transcript appears
```

## 📁 Important Files

| File | Purpose |
|------|---------|
| `demo_app.py` | Main application |
| `.env` | API keys & configuration |
| `database.py` | Database operations |
| `audio_capture_robust.py` | Audio processing |
| `whisper_audio.py` | Transcription |
| `engagement_realtime.py` | Video analysis |

## 🔧 Quick Commands

```bash
# Check Python version
python --version

# Install dependencies
pip install -r requirements.txt

# Run tests
python test_interview_system.py

# Start main app only
streamlit run demo_app.py

# Kill all Python processes
taskkill /F /IM python.exe

# Check running services
tasklist | findstr python
```

## 🌐 Service URLs

| Service | URL | Port |
|---------|-----|------|
| Main App | http://localhost:8501 | 8501 |
| Answer Service | http://localhost:8000 | 8000 |
| Fusion Service | http://localhost:8001 | 8001 |
| Emotion Service | http://localhost:8002 | 8002 |
| Insight Service | http://localhost:8003 | 8003 |
| Engagement Service | http://localhost:8004 | 8004 |

## 🐛 Debug Mode

Add to `.env`:
```
DEBUG_AUDIO=true
DEBUG_WEBRTC=true
```

Watch terminal for:
- `[audio_capture]` - Audio logs
- `[RECORDING]` - Recording logs
- `[whisper_audio]` - Transcription logs

## 📊 Success Indicators

✅ Camera shows your face
✅ Green checkmarks (camera, face, mic)
✅ Recording timer counts down
✅ Transcript appears after recording
✅ Can complete all 5 questions
✅ Report page shows "Interview Complete!"

## ⚠️ Common Errors

**"No speech detected"**
→ Microphone not working or muted

**"Camera not starting"**
→ Permission denied or camera in use

**"Transcription failed"**
→ No internet or API key issue

**"Audio processor missing"**
→ Microphone permission not granted

## 🔍 Quick Diagnostics

**Check API Key:**
```bash
# In .env file
GROQ_API_KEY_2=gsk_...
```

**Check Microphone:**
1. Windows Settings → Sound → Input
2. Test in Voice Recorder
3. Ensure not muted

**Check Camera:**
1. Windows Settings → Privacy → Camera
2. Ensure browser is allowed
3. Close other apps using camera

**Check Services:**
```bash
# Should see 5 Python processes
tasklist | findstr python
```

## 📞 Get Help

1. Check `QUICK_FIX_GUIDE.md`
2. Run `python test_interview_system.py`
3. Check browser console (F12)
4. Check server terminal logs

## 🎯 Interview Flow

```
1. Login → 2. Upload Resume → 3. Camera Check → 
4. Prep (15s) → 5. Record (60s) → 6. Transcript → 
7. Repeat for 5 questions → 8. Report
```

## 💡 Pro Tips

- Use Chrome or Edge (best compatibility)
- Close unnecessary apps before starting
- Use wired internet (more stable)
- Test microphone before interview
- Speak clearly and close to mic
- Stay centered in camera frame
- Good lighting helps face detection

## 🔄 Quick Reset

```bash
# Stop everything
taskkill /F /IM python.exe

# Clear browser cache
Ctrl + Shift + Delete

# Restart
START_INTERVIEW_SYSTEM.bat
```

## 📈 Performance

- Camera init: ~2-3 seconds
- Audio capture: Real-time
- Transcription: ~3-5 seconds
- Total interview: ~15-20 minutes

## ✅ Pre-Flight Checklist

Before starting interview:
- [ ] All services running
- [ ] Groq API key configured
- [ ] Microphone tested
- [ ] Camera tested
- [ ] Good lighting
- [ ] Quiet environment
- [ ] Stable internet

---

**Keep this card handy during interviews!**
