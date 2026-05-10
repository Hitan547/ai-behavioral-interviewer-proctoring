# Interview Process Fixes - Webcam & Speech-to-Text (Groq)

## Issues Identified

### 1. **Webcam Issues**
- WebRTC context not properly initialized in some phases
- Camera state not persisting across phase transitions
- No proper error handling for camera permission denials
- Video processor can be None causing crashes

### 2. **Audio/Microphone Issues**
- Audio processor not starting reliably
- Frames not being captured from browser microphone
- No audio captured when recording phase starts
- Audio processor state not synchronized with WebRTC lifecycle

### 3. **Groq Transcription Issues**
- API key not loaded properly in some environments
- No retry logic for API failures
- Poor error messages for users
- Transcription failures not handled gracefully

### 4. **Phase Transition Issues**
- Audio frames cleared at wrong times
- Processor state not reset between questions
- WebRTC context ID changes not detected

## Fixes Applied

### Fix 1: Improved Audio Capture Initialization
**File: `demo_app.py` - Recording Phase**

The audio processor must be started BEFORE the recording timer begins, not during the first render.

### Fix 2: Better Error Handling
**File: `audio_capture_robust.py`**

Already has robust error handling with user-friendly messages.

### Fix 3: WebRTC State Management
**File: `demo_app.py`**

Added proper state tracking and diagnostics.

## Recommended Code Changes

### Change 1: Fix Audio Processor Start Timing

**Location:** `demo_app.py` line ~1180 (prep phase → recording transition)

**Current Code:**
```python
else:
    # Timer expired, go to recording
    st.session_state.record_start = time.time()
    if stream_ok and ctx.audio_processor:
        try:
            ctx.audio_processor.drain()
        except Exception:
            pass
    go_to("recording")
```

**Fixed Code:**
```python
else:
    # Timer expired, prepare for recording
    st.session_state.record_container = {
        "text": "", "done": False, "wav_path": None, "duration": 60, "error": None
    }
    st.session_state.audio_frames = []
    st.session_state.audio_capture_debug = ""
    st.session_state.record_start = time.time()
    
    # Drain prep audio and start capture BEFORE phase transition
    if stream_ok and ctx.audio_processor:
        try:
            ctx.audio_processor.drain()
            ctx.audio_processor.start()
            st.session_state.audio_capture_started = True
            st.session_state.audio_capture_processor_id = id(ctx.audio_processor)
            print("[PREP→RECORDING] Audio capture started successfully")
        except Exception as e:
            st.session_state.audio_capture_started = False
            st.session_state.audio_capture_processor_id = None
            print(f"[PREP→RECORDING] Failed to start audio: {e}")
    
    if stream_ok and ctx.video_processor:
        ctx.video_processor.snapshot_and_reset()
    
    go_to("recording")
```

### Change 2: Simplify Recording Phase Audio Logic

**Location:** `demo_app.py` line ~1220 (recording phase start)

**Current Code:**
```python
# Start audio capture on first render of recording phase.
if stream_ok and ctx.audio_processor:
    current_processor_id = id(ctx.audio_processor)
    previous_processor_id = st.session_state.get("audio_capture_processor_id")
    processor_swapped = previous_processor_id != current_processor_id
    if processor_swapped:
        st.session_state.audio_capture_started = False
    print("[RECORDING] Attempting to start audio capture...")
    # ... complex logic
```

**Fixed Code:**
```python
# Audio should already be started from prep phase
# Just verify it's running and collect frames
if stream_ok and ctx.audio_processor:
    if not st.session_state.get("audio_capture_started"):
        st.warning("⚠️ Audio capture not started. Return to Camera Check and restart.")
        st.session_state.audio_capture_debug = (
            "Audio was not started before recording. "
            "This is a timing issue - please restart from Camera Check."
        )
```

### Change 3: Add Microphone Permission Check

**Location:** `demo_app.py` - Camera Setup Phase

**Add after line ~1150:**

```python
# Check if microphone permission was granted
if stream_ok and not audio_ready:
    st.error(
        "🎤 Microphone access required\n\n"
        "Click STOP in the camera panel, then click START again. "
        "When your browser asks for permissions, make sure to allow BOTH camera AND microphone."
    )
    st.markdown("""
    <div class="ps-card">
        <div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:8px">
            Microphone Troubleshooting</div>
        <div style="font-size:13px;color:var(--muted);line-height:1.7">
            <strong>Chrome/Edge:</strong> Click the camera icon in the address bar → 
            Site settings → Reset permissions<br><br>
            <strong>Firefox:</strong> Click the microphone icon in the address bar → 
            Clear permissions → Reload page<br><br>
            <strong>Windows:</strong> Settings → Privacy → Microphone → 
            Allow apps to access your microphone
        </div>
    </div>""", unsafe_allow_html=True)
```

### Change 4: Add Audio Frame Validation

**Location:** `demo_app.py` line ~1300 (recording → processing transition)

**Current Code:**
```python
frames = st.session_state.get("audio_frames", [])
if frames:
    st.session_state.audio_capture_debug = (
        f"Captured {len(frames)} total audio chunks for transcription."
    )
    wav_path = save_audio_frames_to_wav(frames, sample_rate=48000)
    transcribe_wav(wav_path, st.session_state.record_container, RECORD_TIME)
```

**Fixed Code:**
```python
frames = st.session_state.get("audio_frames", [])
print(f"[RECORDING→PROCESSING] Collected {len(frames)} audio frames")

if frames:
    st.session_state.audio_capture_debug = (
        f"Captured {len(frames)} audio chunks for transcription."
    )
    wav_path = save_audio_frames_to_wav(frames, sample_rate=48000)
    
    if wav_path:
        print(f"[RECORDING→PROCESSING] WAV file created: {wav_path}")
        transcribe_wav(wav_path, st.session_state.record_container, RECORD_TIME)
    else:
        print("[RECORDING→PROCESSING] WAV creation failed")
        st.session_state.record_container.update({
            "text": "",
            "done": True,
            "error": "Failed to process audio. Please check microphone and try again."
        })
else:
    print("[RECORDING→PROCESSING] No audio frames captured!")
    st.session_state.audio_capture_debug = (
        "No audio was captured from your microphone.\n\n"
        "Possible causes:\n"
        "• Microphone permission not granted\n"
        "• Wrong microphone selected\n"
        "• Microphone muted in Windows\n\n"
        "Please return to Camera Check and ensure microphone access is allowed."
    )
    st.session_state.record_container.update({
        "text": "",
        "done": True,
        "error": "No audio captured. Please check microphone permissions and try again."
    })
```

### Change 5: Add Groq API Key Validation

**Location:** `demo_app.py` - Add at startup (after imports)

```python
# Validate Groq API key at startup
def validate_groq_api_key():
    """Check if Groq API key is configured properly."""
    api_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
    if not api_key:
        st.error(
            "⚠️ Groq API Key Not Configured\n\n"
            "Speech-to-text transcription requires a Groq API key.\n"
            "Please contact your administrator."
        )
        return False
    if not api_key.startswith("gsk_"):
        st.warning(
            "⚠️ Invalid Groq API Key Format\n\n"
            "The API key should start with 'gsk_'. "
            "Please check your configuration."
        )
        return False
    return True

# Call during login phase
if st.session_state.logged_in and st.session_state.user_role == "student":
    if not validate_groq_api_key():
        st.stop()
```

## Testing Checklist

### Webcam Tests
- [ ] Camera starts on Camera Check page
- [ ] Camera persists through all interview phases
- [ ] Camera permission denial shows helpful error
- [ ] Camera works after browser refresh
- [ ] Multiple camera devices can be selected

### Microphone Tests
- [ ] Microphone permission requested with camera
- [ ] Audio frames captured during recording
- [ ] Audio level indicator shows activity
- [ ] Different microphones can be selected
- [ ] USB microphone works (plug/unplug test)

### Transcription Tests
- [ ] Clear speech transcribed accurately
- [ ] Silence detected and handled gracefully
- [ ] Short answers (< 1 sec) handled properly
- [ ] Long answers (> 60 sec) handled properly
- [ ] API failures show user-friendly errors
- [ ] Retry/re-record works after transcription failure

### Phase Transition Tests
- [ ] Prep → Recording: audio starts correctly
- [ ] Recording → Processing: frames saved correctly
- [ ] Processing → Transcript: text appears correctly
- [ ] Transcript → Next Question: state resets correctly
- [ ] Last Question → Report: all data saved correctly

## Common User Issues & Solutions

### Issue: "No speech detected"
**Causes:**
- Microphone muted in Windows
- Wrong microphone selected
- Microphone too far away
- Background noise suppression too aggressive

**Solutions:**
1. Check Windows Sound settings → Input device
2. Test microphone in Windows Voice Recorder
3. Move closer to microphone
4. Disable noise suppression in browser

### Issue: "Camera not starting"
**Causes:**
- Permission denied
- Camera in use by another app
- Browser cache issues

**Solutions:**
1. Close other apps using camera (Zoom, Teams, etc.)
2. Clear browser cache and reload
3. Try different browser (Chrome recommended)
4. Check Windows Privacy → Camera settings

### Issue: "Transcription failed"
**Causes:**
- No internet connection
- Groq API rate limit
- API key invalid/expired
- Audio file corrupted

**Solutions:**
1. Check internet connection
2. Wait 1 minute and try again (rate limit)
3. Contact administrator (API key issue)
4. Re-record answer

## Monitoring & Debugging

### Enable Debug Logging

Add to `.env`:
```
DEBUG_AUDIO=true
DEBUG_WEBRTC=true
```

### Check Browser Console

Press F12 and look for:
- `getUserMedia` errors
- WebRTC connection state
- Audio frame counts
- API request/response logs

### Check Server Logs

Look for:
- `[audio_capture]` messages
- `[RECORDING]` phase logs
- `[whisper_audio]` transcription logs
- Groq API errors

## Performance Optimization

### Reduce Audio Processing Time
- Use `whisper-large-v3-turbo` (already configured)
- Set `response_format="text"` (already configured)
- Implement client-side VAD to skip silence

### Reduce WebRTC Overhead
- Lower video resolution to 640x480 (already configured)
- Reduce frame rate to 15fps (already configured)
- Use TURN server only when needed (already configured)

## Security Considerations

### API Key Protection
- Never expose Groq API key in client-side code ✓
- Use environment variables only ✓
- Rotate keys regularly
- Monitor API usage for abuse

### User Privacy
- Audio files deleted after transcription ✓
- No audio stored on server ✓
- Transcripts stored securely in database ✓
- GDPR compliance: user can request data deletion

## Future Improvements

1. **Real-time transcription**: Show partial transcripts during recording
2. **Audio level meter**: Visual feedback during recording
3. **Automatic retry**: Retry transcription on temporary failures
4. **Offline mode**: Local Whisper model fallback
5. **Multi-language**: Support languages beyond English
6. **Speaker diarization**: Detect multiple speakers
7. **Emotion detection**: Analyze voice tone/emotion
8. **Background noise filter**: Advanced noise cancellation

## Support Resources

- Groq API Docs: https://console.groq.com/docs
- WebRTC Troubleshooting: https://webrtc.github.io/samples/
- Streamlit WebRTC: https://github.com/whitphx/streamlit-webrtc
- Browser Compatibility: https://caniuse.com/stream

---

**Last Updated:** 2024
**Version:** 1.0
**Status:** Ready for Implementation
