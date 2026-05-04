# Quick Fix Guide - Webcam & Speech-to-Text Issues

## Problem Summary
1. **Webcam not opening** - Camera permission issues, WebRTC not initializing
2. **Speech not detected** - Microphone not capturing audio, audio processor not starting
3. **No transcript** - Groq API issues, audio frames not being saved

## Quick Fixes (Apply in Order)

### Fix 1: Verify Groq API Key (CRITICAL)

**Check `.env` file:**
```bash
GROQ_API_KEY=gsk_your_primary_key_here
GROQ_API_KEY_2=gsk_your_audio_key_here
```

✅ Both keys are present and start with `gsk_`

### Fix 2: Test Groq API Manually

Create `test_groq.py`:
```python
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
print(f"API Key: {api_key[:20]}...")

client = Groq(api_key=api_key)

# Test transcription with a sample file
print("Testing Groq Whisper API...")
try:
    # You'll need a test.wav file
    with open("test.wav", "rb") as f:
        result = client.audio.transcriptions.create(
            file=("test.wav", f),
            model="whisper-large-v3-turbo",
            language="en",
            response_format="text",
        )
    print(f"Success! Transcript: {result}")
except Exception as e:
    print(f"Error: {e}")
```

Run: `python test_groq.py`

### Fix 3: Check Browser Permissions

**Chrome/Edge:**
1. Go to `chrome://settings/content/camera`
2. Ensure site is not blocked
3. Go to `chrome://settings/content/microphone`
4. Ensure site is not blocked

**Firefox:**
1. Go to `about:preferences#privacy`
2. Scroll to Permissions → Camera → Settings
3. Remove any blocks for localhost
4. Do the same for Microphone

### Fix 4: Test Microphone in Windows

1. Open **Sound Settings** (Right-click speaker icon)
2. Go to **Input** section
3. Select your microphone
4. Click **Test** and speak - you should see the blue bar move
5. If no movement, your microphone is not working

### Fix 5: Restart Services

```bash
# Stop all services
taskkill /F /IM python.exe

# Restart
run_system.bat
```

### Fix 6: Clear Browser Cache

1. Press `Ctrl + Shift + Delete`
2. Select "Cached images and files"
3. Select "Cookies and other site data"
4. Click "Clear data"
5. Restart browser
6. Go to `http://localhost:8501`

### Fix 7: Test WebRTC

Go to: https://test.webrtc.org/

This will test:
- Camera access
- Microphone access
- Network connectivity
- WebRTC support

If this fails, your browser/system has issues with WebRTC.

## Common Error Messages & Solutions

### "No speech detected"

**Cause:** Microphone not capturing audio

**Solution:**
1. Check Windows Sound Settings → Input device
2. Test microphone in Voice Recorder app
3. Ensure microphone is not muted (hardware button)
4. Check browser permissions (see Fix 3)
5. Try a different microphone (USB headset)

### "Camera not starting"

**Cause:** Camera permission denied or in use

**Solution:**
1. Close Zoom, Teams, Skype, or other video apps
2. Close other browser tabs using camera
3. Click "Reset Camera" button in the app
4. Restart browser
5. Check Windows Privacy → Camera settings

### "Transcription failed"

**Cause:** Groq API issue

**Solution:**
1. Check internet connection
2. Verify API key in `.env` (see Fix 1)
3. Test API manually (see Fix 2)
4. Wait 1 minute (rate limit) and try again
5. Check Groq console: https://console.groq.com/

### "Audio processor missing"

**Cause:** WebRTC audio stream not initialized

**Solution:**
1. Go back to Camera Check
2. Click STOP in camera panel
3. Click START again
4. Allow microphone permission when prompted
5. Wait for "Mic stream ready" checkmark

## Debug Mode

Add to `.env`:
```
DEBUG_AUDIO=true
DEBUG_WEBRTC=true
```

Then check terminal output for detailed logs:
- `[audio_capture]` - Audio processing logs
- `[RECORDING]` - Recording phase logs
- `[whisper_audio]` - Transcription logs
- `[PREP→RECORDING]` - Phase transition logs

## Still Not Working?

### Last Resort Fixes:

1. **Use a different browser**
   - Chrome is recommended
   - Edge also works well
   - Firefox may have WebRTC issues

2. **Use a different computer**
   - Test on another machine
   - Rules out hardware issues

3. **Use external devices**
   - USB webcam instead of built-in
   - USB microphone or headset
   - These often work better

4. **Check firewall/antivirus**
   - Temporarily disable
   - Add exception for Python/Streamlit
   - Add exception for browser

5. **Update everything**
   - Windows Update
   - Browser update
   - Webcam drivers (Device Manager)
   - Microphone drivers

## Contact Support

If none of the above works, provide this info:

```
OS: Windows [version]
Browser: [Chrome/Edge/Firefox] [version]
Webcam: [Built-in/USB] [model]
Microphone: [Built-in/USB] [model]
Error message: [exact text]
Browser console errors: [F12 → Console tab]
Server terminal errors: [copy last 50 lines]
```

## Success Indicators

You'll know it's working when:

✅ Camera shows your face in the camera panel
✅ Green checkmarks for Camera, Face, and Microphone
✅ Recording timer counts down from 60 to 0
✅ "Transcribing..." message appears after recording
✅ Your spoken words appear as text in the transcript
✅ Engagement score shows (e.g., "7.5 / 10")
✅ Can complete all 5 questions without errors
✅ Report page shows "Interview Complete!"

## Performance Tips

To improve reliability:

1. **Close unnecessary apps** - Free up system resources
2. **Use wired internet** - More stable than WiFi
3. **Good lighting** - Helps face detection
4. **Quiet environment** - Improves transcription accuracy
5. **Speak clearly** - Pause between sentences
6. **Stay centered** - Keep face in frame
7. **Test first** - Do a practice run before real interview

---

**Last Updated:** 2024
**Version:** 1.0
