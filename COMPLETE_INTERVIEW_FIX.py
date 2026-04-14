"""
COMPLETE INTERVIEW FIX - Webcam & Speech-to-Text
=================================================

This file contains all the fixes needed for the interview process.
Apply these changes to demo_app.py to fix:
1. Webcam not opening
2. Speech-to-text not detecting speech
3. No transcript being generated
4. Overall interview process issues

INSTRUCTIONS:
1. Backup your current demo_app.py
2. Apply the changes below in order
3. Test the interview flow end-to-end
"""

# ============================================================================
# FIX 1: Enhanced Camera Setup Section
# ============================================================================
# Replace the entire camera_setup phase (lines 1020-1090) with this:

CAMERA_SETUP_FIX = '''
        # ── CAMERA SETUP ──────────────────────────────────────────────
        if phase == "camera_setup":
            render_stepper(1)
            page_title("Camera Check", "Allow camera & microphone access")
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            
            # Clear, actionable instructions
            st.markdown("""
            <div class="ps-card" style="border-left:3px solid var(--indigo)">
              <div style="font-size:14px;font-weight:700;color:var(--indigo);margin-bottom:8px">
                📹 Step 1: Enable Camera & Microphone</div>
              <div style="font-size:13px;color:var(--text);line-height:1.7">
                1. Click the <strong style="color:var(--indigo)">START</strong> button in the camera panel (right side) →<br>
                2. When your browser asks for permission, click <strong>Allow</strong> for BOTH camera and microphone<br>
                3. Wait for the green checkmarks below
              </div>
            </div>""", unsafe_allow_html=True)
            
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

            if stream_ok:
                c1, c2, c3 = st.columns(3)
                c1.success("✓ Camera active")
                c2.success("✓ Face detected")
                if audio_ready:
                    c3.success("✓ Microphone ready")
                else:
                    c3.error("✗ Microphone not ready")
                
                if audio_ready:
                    st.markdown("""
                    <div style="margin-top:16px;padding:16px 20px;background:#effaf4;
                         border-radius:12px;border:1px solid #b6f0cc">
                      <div style="font-size:14px;font-weight:600;color:#166534">
                        ✅ All systems ready! You can start the interview.</div>
                    </div>""", unsafe_allow_html=True)
                    
                    if not st.session_state.get("camera_ready_confirmed"):
                        st.session_state.camera_ready_confirmed = True
                    
                    if st.button("▶  Start Interview", type="primary", use_container_width=True, key="cam_proceed"):
                        if st.session_state.get("jd_id"):
                            update_interview_status(
                                st.session_state.auth_username,
                                st.session_state.jd_id,
                                "In Progress"
                            )
                        go_to("prep")
                else:
                    st.error(
                        "🎤 **Microphone Required**\\n\\n"
                        "The microphone is not ready. Without it, we cannot record your answers.\\n\\n"
                        "**How to fix:**\\n"
                        "1. Click **STOP** in the camera panel\\n"
                        "2. Click **START** again\\n"
                        "3. When prompted, allow **BOTH** camera AND microphone"
                    )
                    
                    with st.expander("🔧 Detailed Microphone Troubleshooting"):
                        st.markdown("""
                        ### Browser Permissions
                        
                        **Chrome/Edge:**
                        1. Click the camera/microphone icon in the address bar (left side)
                        2. Click "Site settings"
                        3. Find "Camera" and "Microphone" - set both to "Allow"
                        4. Reload this page (F5) and click START again
                        
                        **Firefox:**
                        1. Click the microphone icon in the address bar
                        2. Click "Clear These Settings"
                        3. Reload this page (F5) and click START again
                        
                        ### Windows Settings
                        
                        1. Open **Settings** → **Privacy** → **Microphone**
                        2. Ensure "Allow apps to access your microphone" is **ON**
                        3. Scroll down and ensure your browser is **allowed**
                        
                        ### Test Your Microphone
                        
                        1. Open **Windows Voice Recorder** app
                        2. Try recording - if it works, your mic is fine
                        3. If it doesn't work, check **Sound Settings** → **Input device**
                        4. Make sure the correct microphone is selected as default
                        
                        ### Still Not Working?
                        
                        - Try a different browser (Chrome recommended)
                        - Restart your browser completely
                        - Restart your computer
                        - Check if your microphone is muted (hardware button)
                        """)
            else:
                # Camera not started
                if stream_waiting:
                    st.warning("⏳ Camera permission granted but not fully initialized. Wait 2-3 seconds, then click STOP and START again.")
                else:
                    st.markdown("""
                    <div class="ps-card" style="background:#fef2f2;border:1px solid #fecaca">
                      <div style="font-size:14px;font-weight:600;color:#991b1b;margin-bottom:8px">
                        ⚠️ Camera Not Started</div>
                      <div style="font-size:13px;color:#7f1d1d;line-height:1.7">
                        Look at the camera panel on the right →<br>
                        Click the <strong>START</strong> button.<br>
                        When your browser asks for permission, click <strong>Allow</strong>.
                      </div>
                    </div>""", unsafe_allow_html=True)
                
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 Refresh Page", use_container_width=True):
                        st.rerun()
                with col2:
                    if st.button("⚠️ Reset Camera", key="reset_webrtc_devices", use_container_width=True):
                        st.info("Resetting camera... Wait 3 seconds and click START again.")
                        st.session_state.webrtc_reset_nonce += 1
                        st.session_state.audio_capture_started = False
                        st.session_state.audio_capture_processor_id = None
                        st.session_state._last_webrtc_diag = None
                        st.session_state._last_webrtc_ctx_id = None
                        time.sleep(2)
                        st.rerun()
                
                with st.expander("🔧 Camera Troubleshooting"):
                    st.markdown("""
                    ### Common Camera Issues
                    
                    **1. "Requested device not found"**
                    - Click **SELECT DEVICE** in the camera panel
                    - Choose your webcam from the dropdown list
                    
                    **2. Camera in use by another application**
                    - Close Zoom, Microsoft Teams, Skype, or other video apps
                    - Close other browser tabs that might be using the camera
                    - Check Windows Task Manager for apps using the camera
                    
                    **3. Permission denied**
                    - Click the camera icon in your browser's address bar
                    - Reset permissions for this site
                    - Reload the page (F5) and try again
                    
                    **4. Black screen or no video**
                    - Open **Windows Settings** → **Privacy** → **Camera**
                    - Ensure "Allow apps to access your camera" is **ON**
                    - Ensure your browser is in the allowed list
                    
                    **5. Camera works in other apps but not here**
                    - Try a different browser (Chrome is recommended)
                    - Clear your browser cache and cookies
                    - Update your browser to the latest version
                    
                    **6. Still not working?**
                    - Restart your browser completely (close all windows)
                    - Restart your computer
                    - Update your webcam drivers from Device Manager
                    - Try using an external USB webcam if available
                    """)
                
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                
                # Best practices tips
                tc1, tc2, tc3 = st.columns(3)
                for col, icon, title, tip in [
                    (tc1, "💡", "Good Lighting", "Face a window or lamp, avoid backlight"),
                    (tc2, "👁", "Proper Framing", "Center your face, show shoulders"),
                    (tc3, "🔇", "Quiet Environment", "Minimize background noise"),
                ]:
                    with col:
                        st.markdown(f"""
                        <div class="ps-card" style="text-align:center;padding:18px 14px">
                          <div style="font-size:22px;margin-bottom:8px">{icon}</div>
                          <div style="font-size:13px;font-weight:600;color:var(--text)">{title}</div>
                          <div style="font-size:11px;color:var(--muted);margin-top:4px;line-height:1.5">{tip}</div>
                        </div>""", unsafe_allow_html=True)
                
                # Debug info for troubleshooting
                st.caption(
                    f"Debug: playing={ctx.state.playing}, signalling={ctx.state.signalling}, "
                    f"video={video_ready}, audio={audio_ready}"
                )
'''

# ============================================================================
# FIX 2: Improved Audio Capture in Recording Phase
# ============================================================================
# The recording phase audio capture logic has already been fixed in previous changes
# Ensure these lines are present in the recording phase:

RECORDING_PHASE_AUDIO_FIX = '''
            # Verify audio capture is running (should have been started in prep phase)
            if stream_ok and ctx.audio_processor:
                if not st.session_state.get("audio_capture_started"):
                    st.error(
                        "⚠️ **Microphone Not Capturing**\\n\\n"
                        "Audio capture was not started properly.\\n\\n"
                        "**What to do:**\\n"
                        "1. Note your current answer\\n"
                        "2. Return to Camera Check\\n"
                        "3. Restart the interview\\n"
                        "4. Make sure microphone permission is granted"
                    )
                    st.session_state.audio_capture_debug = (
                        "Audio capture not started before recording phase. "
                        "This is a timing issue - please restart from Camera Check."
                    )
            elif stream_ok and not ctx.audio_processor:
                st.error(
                    "🎤 **Microphone Stream Missing**\\n\\n"
                    "The microphone stream is not available.\\n\\n"
                    "**How to fix:**\\n"
                    "1. Click STOP in the camera panel\\n"
                    "2. Click START again\\n"
                    "3. Allow microphone access when prompted"
                )
                st.session_state.audio_capture_debug = (
                    "Microphone stream is not ready (audio processor missing). "
                    "Click STOP, then START and re-allow microphone access."
                )
'''

# ============================================================================
# FIX 3: Better Transcript Display with Error Handling
# ============================================================================
# Replace the transcript phase error display section:

TRANSCRIPT_PHASE_FIX = '''
            has_ans  = bool(ans and ans.strip())
            t_bg     = "#effaf4" if has_ans else "#fef2f2"
            t_border = "#b6f0cc" if has_ans else "#fecaca"
            t_text   = "#1a3a20" if has_ans else "#7f1d1d"
            t_label  = "#16a34a" if has_ans else "#dc2626"
            
            if has_ans:
                t_body = ans
            else:
                t_body = "⚠️ No speech was detected in your recording."

            st.markdown(f"""
            <div style="background:{t_bg};border:1px solid {t_border};border-radius:12px;
                 padding:16px 20px;margin-bottom:16px">
              <div style="font-size:10px;font-weight:700;color:{t_label};
                   text-transform:uppercase;letter-spacing:0.8px;margin-bottom:9px">
                Your Transcript</div>
              <div style="font-size:14px;color:{t_text};line-height:1.75">{t_body}</div>
            </div>""", unsafe_allow_html=True)

            if error_msg:
                st.error(f"**Transcription Error:** {error_msg}")
                
                if "microphone" in error_msg.lower() or "audio" in error_msg.lower():
                    with st.expander("🔧 Audio Troubleshooting"):
                        st.markdown("""
                        ### Why is there no audio?
                        
                        **Most Common Causes:**
                        
                        1. **Microphone permission not granted**
                           - Go back to Camera Check
                           - Click STOP then START
                           - Allow microphone when prompted
                        
                        2. **Wrong microphone selected**
                           - Open Windows Sound Settings
                           - Go to Input devices
                           - Set your microphone as default
                           - Test it in Voice Recorder
                        
                        3. **Microphone muted**
                           - Check if your microphone has a hardware mute button
                           - Check Windows Sound Settings → Input device → Test
                           - Ensure volume is not at 0%
                        
                        4. **Browser not allowed to access microphone**
                           - Windows Settings → Privacy → Microphone
                           - Ensure "Allow apps to access your microphone" is ON
                           - Ensure your browser is in the allowed list
                        
                        ### What to do now?
                        
                        1. Fix the microphone issue using the steps above
                        2. Click "Re-record" below to try again
                        3. Speak clearly and close to the microphone
                        4. Check that the audio level indicator shows activity
                        """)
            
            if not has_ans:
                if st.session_state.get("audio_capture_debug"):
                    st.info(f"**Debug Info:** {st.session_state.audio_capture_debug}")
                
                st.warning(
                    "**No Speech Detected**\\n\\n"
                    "Possible reasons:\\n"
                    "• Microphone was muted or not working\\n"
                    "• You spoke too quietly\\n"
                    "• Background noise was too loud\\n"
                    "• Microphone permission was not granted\\n\\n"
                    "Use the Re-record button below to try again."
                )
'''

# ============================================================================
# FIX 4: Add Groq API Key Validation at Startup
# ============================================================================
# Add this function after the imports section:

GROQ_VALIDATION_FIX = '''
# ══════════════════════════════════════════════════════════════════════════
# GROQ API KEY VALIDATION
# ══════════════════════════════════════════════════════════════════════════
def validate_groq_api_key():
    """Validate Groq API key is configured and formatted correctly."""
    import os
    api_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
    
    if not api_key:
        return False, "Groq API key not found in environment variables"
    
    if not api_key.startswith("gsk_"):
        return False, f"Invalid API key format (should start with 'gsk_')"
    
    if len(api_key) < 20:
        return False, "API key appears to be incomplete"
    
    return True, "API key validated"

# Validate API key when student logs in
if st.session_state.logged_in and st.session_state.user_role == "student":
    is_valid, message = validate_groq_api_key()
    if not is_valid:
        st.error(
            f"⚠️ **Speech-to-Text Not Available**\\n\\n"
            f"{message}\\n\\n"
            f"Please contact your administrator to configure the Groq API key."
        )
        st.stop()
'''

# ============================================================================
# TESTING CHECKLIST
# ============================================================================
TESTING_CHECKLIST = """
TESTING CHECKLIST - Complete Interview Flow
============================================

Test each step in order:

□ 1. LOGIN
   - Student can log in successfully
   - Redirected to start page

□ 2. START PAGE
   - Upload resume (PDF)
   - Enter candidate name
   - Optional: paste/upload JD
   - Click "Generate Questions"
   - 5 questions generated successfully

□ 3. CAMERA CHECK
   - Click START in camera panel
   - Browser asks for camera permission → Allow
   - Browser asks for microphone permission → Allow
   - Green checkmarks appear for camera, face, and microphone
   - "Start Interview" button appears and is clickable

□ 4. PREP PHASE (Question 1)
   - Question displays clearly
   - 15-second countdown timer works
   - Timer reaches 0 and automatically transitions to recording

□ 5. RECORDING PHASE (Question 1)
   - Red "REC" indicator shows in camera panel
   - 60-second countdown timer works
   - Speak your answer clearly for 10-15 seconds
   - Timer reaches 0 and transitions to processing

□ 6. PROCESSING PHASE
   - "Transcribing your answer..." message shows
   - Processing completes within 5-10 seconds
   - Transitions to transcript review

□ 7. TRANSCRIPT REVIEW (Question 1)
   - Your spoken answer appears as text
   - Text is accurate (at least 80% correct)
   - Engagement score shows (e.g., "7.5 / 10")
   - Face presence shows (e.g., "95%")
   - "Submit & Next Question" button works

□ 8. QUESTIONS 2-5
   - Repeat steps 4-7 for remaining questions
   - Each question cycles through: Prep → Recording → Processing → Transcript
   - Re-record button works if needed (once per question)

□ 9. REPORT PAGE
   - "Interview Complete!" message shows
   - All 5 questions answered
   - Status shows "Submitted"
   - Can start new interview or logout

□ 10. RECRUITER DASHBOARD
   - Login as recruiter (username: recruiter, password: admin123)
   - See the completed interview in the list
   - Click "Full Report" to view details
   - All transcripts are visible
   - Scores are calculated correctly

COMMON ISSUES TO TEST:

□ Microphone Issues
   - Deny microphone permission → Error message shows
   - Mute microphone → "No speech detected" message
   - Wrong microphone selected → Can change in browser settings

□ Camera Issues
   - Deny camera permission → Error message shows
   - Camera in use by another app → Error message shows
   - Can reset camera using "Reset Camera" button

□ Network Issues
   - Slow internet → Processing takes longer but completes
   - No internet → Clear error message about connection

□ Browser Compatibility
   - Test in Chrome (recommended)
   - Test in Edge
   - Test in Firefox

PASS CRITERIA:
- All checkboxes above are checked ✓
- No errors in browser console (F12)
- No errors in server terminal
- Transcripts are accurate (>80%)
- Interview completes end-to-end without crashes
"""

print(TESTING_CHECKLIST)
