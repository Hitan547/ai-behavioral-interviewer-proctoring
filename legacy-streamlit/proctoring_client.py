"""
proctoring_client.py — Client-side anti-cheating proctoring module
 
Injects CSS overlays, HTML elements, and JavaScript event listeners
into the Streamlit page for real-time proctoring during interviews.
 
Features:
  - Tab switch detection (visibilitychange API)
  - Window switch detection (blur/focus on parent window)
  - Copy/paste blocking with toast notifications
  - Right-click blocking
  - DevTools shortcut blocking (F12, Ctrl+Shift+I, Ctrl+U)
  - Progressive warning overlays (yellow → orange → red)
  - Dismiss cooldown to prevent focus re-trigger
  - JS → Streamlit session_state sync via st.query_params
 
Fix log:
  - Removed duplicate `fullscreenExits: 0` key in __psProctoring init
    (first entry was silently overwritten by a second one six lines later).
  - render_proctoring_chips() no longer reads stale session_state values;
    it now receives live counters directly, caller passes them in.
  - Added _sync_proctoring_state() helper: reads window.__psProctoring
    via a postMessage bridge so Python always has current counters.
"""
 
import json
from urllib.parse import unquote

import streamlit as st
import streamlit.components.v1 as components
 
 
# ─────────────────────────────────────────────────────────
# CSS + HTML overlay injection (via st.markdown)
# ─────────────────────────────────────────────────────────
 
_PROCTORING_CSS_HTML = """
<style>
/* ── Proctoring warning overlays ── */
#ps-proctor-overlay {
  display: none;
  position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
  z-index: 999999; justify-content: center; align-items: center;
  backdrop-filter: blur(8px);
}
#ps-proctor-overlay.ps-warn-yellow {
  display: flex;
  background: rgba(245, 158, 11, 0.15);
}
#ps-proctor-overlay.ps-warn-orange {
  display: flex;
  background: rgba(234, 88, 12, 0.35);
}
#ps-proctor-overlay.ps-warn-red {
  display: flex;
  background: rgba(220, 38, 38, 0.5);
}
.ps-proctor-card {
  background: #fff; border-radius: 16px; padding: 32px 40px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.25); text-align: center;
  max-width: 440px; width: 90%;
  font-family: 'DM Sans', -apple-system, sans-serif;
}
.ps-proctor-card h3 { margin: 0 0 8px; font-size: 18px; font-weight: 700; }
.ps-proctor-card p  { margin: 0 0 18px; font-size: 14px; color: #555; line-height: 1.6; }
.ps-proctor-btn {
  padding: 10px 28px; border: none; border-radius: 10px;
  font-size: 14px; font-weight: 600; cursor: pointer;
  transition: transform 0.1s;
}
.ps-proctor-btn:hover { transform: scale(1.02); }
.ps-proctor-btn-orange { background: #ea580c; color: #fff; }
.ps-proctor-btn-red    { background: #dc2626; color: #fff; }
 
/* Fullscreen exit banner */
#ps-fullscreen-banner {
  display: none; position: fixed; top: 0; left: 0; width: 100%;
  z-index: 999998; background: #fef3c7; border-bottom: 2px solid #f59e0b;
  padding: 8px 16px; text-align: center;
  font-family: 'DM Sans', sans-serif; font-size: 13px;
  font-weight: 600; color: #92400e;
}
 
/* Proctoring status chips (camera panel) */
.ps-proctor-chips {
  display: flex; gap: 6px; flex-wrap: wrap; padding: 6px 12px;
  background: #0f0f1c; border: 1px solid #252535; border-top: none;
}
.ps-proctor-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 12px;
  font-size: 10px; font-weight: 600; font-family: var(--mono);
}
.ps-chip-ok   { background: rgba(34,197,94,0.15); color: #4ade80; }
.ps-chip-warn { background: rgba(245,158,11,0.15); color: #fbbf24; }
.ps-chip-bad  { background: rgba(239,68,68,0.15); color: #f87171; }
 
/* Block text selection on question text during interview */
.ps-no-select { user-select: none !important; -webkit-user-select: none !important; }
 
/* ── Secure mode banner (persistent top bar) ── */
#ps-secure-banner {
  display: none; position: fixed; top: 0; left: 0; width: 100%;
  z-index: 999990;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  padding: 6px 20px; text-align: center;
  font-family: 'DM Sans', -apple-system, sans-serif;
  font-size: 12px; font-weight: 600; color: #94a3b8;
  letter-spacing: 0.5px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.3);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
#ps-secure-banner.ps-active { display: block; }
#ps-secure-banner .ps-lock { color: #818cf8; margin-right: 6px; }
#ps-secure-banner .ps-score { color: #f59e0b; margin-left: 12px; }
 
/* ── Fullscreen re-enter overlay (blocks interview) ── */
#ps-fullscreen-overlay {
  display: none; position: fixed; top: 0; left: 0;
  width: 100vw; height: 100vh; z-index: 999999;
  justify-content: center; align-items: center;
  background: rgba(15, 23, 42, 0.92);
  backdrop-filter: blur(12px);
}
#ps-fullscreen-overlay.ps-active { display: flex; }
.ps-fs-card {
  background: #fff; border-radius: 16px; padding: 36px 44px;
  box-shadow: 0 12px 48px rgba(0,0,0,0.4); text-align: center;
  max-width: 460px; width: 90%;
  font-family: 'DM Sans', -apple-system, sans-serif;
}
.ps-fs-card .ps-fs-icon { font-size: 48px; margin-bottom: 12px; }
.ps-fs-card h3 { margin: 0 0 8px; font-size: 18px; font-weight: 700; color: #dc2626; }
.ps-fs-card p { margin: 0 0 20px; font-size: 14px; color: #555; line-height: 1.6; }
.ps-fs-btn {
  padding: 12px 32px; border: none; border-radius: 10px;
  font-size: 14px; font-weight: 700; cursor: pointer;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #fff; transition: transform 0.1s;
}
.ps-fs-btn:hover { transform: scale(1.03); }
</style>
 
<!-- Secure mode banner (shown during active interview) -->
<div id="ps-secure-banner">
  <span class="ps-lock">&#x1F512;</span>
  Interview Integrity Mode &mdash; activity signals are recorded for recruiter review
  <span class="ps-score" id="ps-risk-badge"></span>
</div>
 
<!-- Proctoring overlay (shown on tab-switch / window-switch return) -->
<div id="ps-proctor-overlay">
  <div class="ps-proctor-card" id="ps-proctor-card">
    <h3 id="ps-proctor-title">Please Stay on This Interview</h3>
    <p id="ps-proctor-msg">Leaving the interview window is recorded as an integrity signal.</p>
    <button class="ps-proctor-btn ps-proctor-btn-orange" id="ps-proctor-dismiss">
      I Understand
    </button>
  </div>
</div>
 
<!-- Fullscreen re-enter overlay (blocks interview until fullscreen restored) -->
<div id="ps-fullscreen-overlay">
  <div class="ps-fs-card">
    <div class="ps-fs-icon">&#9888;&#65039;</div>
    <h3>Fullscreen Mode Required</h3>
    <p id="ps-fs-msg">Please re-enter fullscreen to continue the interview.</p>
    <button class="ps-fs-btn" id="ps-fs-reenter">Re-enter Fullscreen</button>
  </div>
</div>
 
<!-- Hidden span for tab-switch count -->
<span id="ps-tab-count" style="display:none">0</span>
"""
 
 
# ─────────────────────────────────────────────────────────
# JavaScript proctoring engine (via components.html)
# ─────────────────────────────────────────────────────────
 
def _build_proctoring_js(is_active: bool, reset_state: bool = False) -> str:
    """Generate the proctoring JavaScript with current active state."""
    active_str = "true" if is_active else "false"
    reset_str = "true" if reset_state else "false"
    return f"""
<script>
(function() {{
  var win = window.parent || window;
  var doc = win.document;
  var shouldBeActive = {active_str};
  var shouldResetState = {reset_str};
 
  // ── State: create once, update always ──
  if (shouldResetState || !win.__psProctoring) {{
    win.__psProctoring = {{
      tabSwitches:       0,
      pasteAttempts:     0,
      fullscreenExits:   0,    // FIX: was listed twice (duplicate key); second entry silently overwrote the first
      screenCount:       1,
      tabLeftAt:         null,
      devToolsAttempts:  0,
      isInterviewActive: shouldBeActive,
      events:            [],
      _dismissCooldown:  0,
      _fullscreenActive: false,
      riskScore:         0
    }};
    console.log('[PsySense] Proctoring state created. Active:', shouldBeActive);
  }} else {{
    win.__psProctoring.isInterviewActive = shouldBeActive;
    console.log('[PsySense] Proctoring re-synced. Active:', shouldBeActive,
                '| tabs:', win.__psProctoring.tabSwitches);
  }}
 
  var S = win.__psProctoring;
 
  function logEv(type, detail) {{
    S.events.push({{ type: type, ts: Date.now(), detail: detail || '' }});
    syncStateToStreamlit();
  }}

  function compactState() {{
    return {{
      tabSwitches: S.tabSwitches || 0,
      pasteAttempts: S.pasteAttempts || 0,
      fullscreenExits: S.fullscreenExits || 0,
      screenCount: S.screenCount || 1,
      devToolsAttempts: S.devToolsAttempts || 0,
      riskScore: S.riskScore || 0,
      events: (S.events || []).slice(-25)
    }};
  }}

  function syncStateToStreamlit() {{
    try {{
      var url = new URL(win.location.href);
      url.searchParams.set('ps_proctor_payload', JSON.stringify(compactState()));
      win.history.replaceState(win.history.state, '', url.toString());
    }} catch(e) {{
      console.warn('[PsySense] Proctoring URL sync failed:', e);
    }}
  }}
 
  // ── Remove old listeners (they die when old iframe is GC'd) ──
  if (win.__psL) {{
    doc.removeEventListener('visibilitychange', win.__psL.vis);
    win.removeEventListener('blur', win.__psL.blur);
    win.removeEventListener('focus', win.__psL.focus);
    doc.removeEventListener('paste', win.__psL.paste, true);
    doc.removeEventListener('copy', win.__psL.copy, true);
    doc.removeEventListener('contextmenu', win.__psL.ctx);
    doc.removeEventListener('keydown', win.__psL.key, true);
    doc.removeEventListener('fullscreenchange', win.__psL.fsc);
    doc.removeEventListener('webkitfullscreenchange', win.__psL.fsc);
    doc.removeEventListener('msfullscreenchange', win.__psL.fsc);
    if (win.__psL.mouseLeave) doc.removeEventListener('mouseleave', win.__psL.mouseLeave);  // ← ADD
    if (win.__psL.mouseEnter) doc.removeEventListener('mouseenter', win.__psL.mouseEnter);  // ← ADD
    if (win.__psL.dismissBtn) win.__psL.dismissBtn.removeEventListener('click', win.__psL.dismiss);
    if (win.__psL.fsBtn) win.__psL.fsBtn.removeEventListener('click', win.__psL.fsReenter);
  }}
 
  // ── Helper: show overlay ──
  function showOverlay(cls, titleText, titleColor, msgText, btnClass, btnText, autoClose) {{
    var ov = doc.getElementById('ps-proctor-overlay');
    var ti = doc.getElementById('ps-proctor-title');
    var mg = doc.getElementById('ps-proctor-msg');
    var bt = doc.getElementById('ps-proctor-dismiss');
    if (!ov) {{ console.warn('[PsySense] Overlay element not found'); return; }}
    ov.className = cls; ov.style.display = 'flex';
    if (ti) {{ ti.textContent = titleText; ti.style.color = titleColor; }}
    if (mg) mg.textContent = msgText;
    if (bt && autoClose) {{ bt.style.display = 'none'; }}
    else if (bt && btnClass) {{ bt.className = btnClass; bt.textContent = btnText; bt.style.display = ''; }}
    if (autoClose) {{
      setTimeout(function() {{
        ov.className = ''; ov.style.display = 'none';
        if (bt) bt.style.display = '';
        S._dismissCooldown = Date.now();
      }}, 3000);
    }}
  }}
 
  // ── Helper: show toast ──
  function showToast(text) {{
    var t = doc.createElement('div');
    t.style.cssText = 'position:fixed;top:20px;right:20px;z-index:999999;background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:10px 18px;font-size:13px;font-weight:600;color:#991b1b;font-family:DM Sans,sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:opacity 0.3s;';
    t.textContent = text;
    doc.body.appendChild(t);
    setTimeout(function() {{ t.style.opacity = '0'; setTimeout(function() {{ t.remove(); }}, 300); }}, 2500);
  }}
 
  // ── Helper: handle switch detection (shared by tab + window) ──
  function handleSwitch(eventType, awayMs) {{
    S.tabSwitches++;
    logEv(eventType, 'Away ' + (awayMs/1000).toFixed(1) + 's');
    console.log('[PsySense] ' + eventType.toUpperCase() + ' #' + S.tabSwitches +
                ' (away ' + (awayMs/1000).toFixed(1) + 's)');
 
    if (S.tabSwitches === 1) {{
      showOverlay('ps-warn-yellow', 'Switch Detected', '#b45309',
        'Switching away during the interview is recorded and visible to the recruiter.',
        null, null, true);
    }} else if (S.tabSwitches === 2) {{
      showOverlay('ps-warn-orange', 'Second Switch Detected', '#c2410c',
        'Further switches will be flagged as suspicious activity.',
        'ps-proctor-btn ps-proctor-btn-orange', 'I Understand', false);
    }} else {{
      showOverlay('ps-warn-red', 'Interview Flagged', '#dc2626',
        'This interview is flagged. All events are logged for recruiter review.',
        'ps-proctor-btn ps-proctor-btn-red', 'Resume Interview', false);
    }}
    updateRiskScore();
    syncStateToStreamlit();
  }}
 
  // 1) Tab visibility (browser tab switches)
  var onVis = function() {{
    if (!S.isInterviewActive) return;
    if (doc.hidden) {{
      S.tabLeftAt = Date.now();
    }} else if (S.tabLeftAt) {{
      if (Date.now() - S._dismissCooldown < 1000) {{ S.tabLeftAt = null; return; }}
      var away = Date.now() - S.tabLeftAt;
      S.tabLeftAt = null;
      handleSwitch('tab_switch', away);
    }}
  }};
 
  // 2) Window blur (Alt+Tab to other apps)
  var onBlur = function() {{
    if (!S.isInterviewActive) return;
    if (!S.tabLeftAt) {{
      S.tabLeftAt = Date.now();
      console.log('[PsySense] Window blur (Alt+Tab)');
    }}
  }};
 
  // 3) Window focus (Alt+Tab BACK — only fires for window switches, not tab switches)
  var onFocus = function() {{
    if (!S.isInterviewActive) return;
    if (Date.now() - S._dismissCooldown < 1000) {{ S.tabLeftAt = null; return; }}
    if (S.tabLeftAt) {{
      var away = Date.now() - S.tabLeftAt;
      S.tabLeftAt = null;
      if (!doc.hidden) {{
        handleSwitch('window_switch', away);
      }}
    }}
  }};
 
  // 4) Paste blocking
  var onPaste = function(e) {{
    if (!S.isInterviewActive) return;
    e.preventDefault(); S.pasteAttempts++; logEv('paste_blocked', '');
    console.log('[PsySense] Paste blocked #' + S.pasteAttempts);
    showToast('Paste is disabled during the interview');
    updateRiskScore();
    syncStateToStreamlit();
  }};
 
  // 5) Copy blocking
  var onCopy = function(e) {{
    if (!S.isInterviewActive) return;
    e.preventDefault(); logEv('copy_blocked', '');
    console.log('[PsySense] Copy blocked');
    showToast('Copy is disabled during the interview');
    updateRiskScore();
    syncStateToStreamlit();
  }};
 
  // 6) Right-click blocking
  var onCtx = function(e) {{
    if (!S.isInterviewActive) return;
    e.preventDefault();
  }};
 
  // 7) Keyboard shortcut detection
  var onKey = function(e) {{
    if (!S.isInterviewActive) return;
    var blocked = false;
    var combo = '';
    if (e.key === 'F12') {{ blocked = true; combo = 'F12'; }}
    if (e.ctrlKey && e.shiftKey && 'IJCijc'.indexOf(e.key) >= 0) {{
      blocked = true; combo = 'Ctrl+Shift+' + e.key.toUpperCase();
    }}
    if (e.ctrlKey && (e.key === 'u' || e.key === 'U')) {{
      blocked = true; combo = 'Ctrl+U';
    }}
    if (blocked) {{
      e.preventDefault(); e.stopPropagation();
      S.devToolsAttempts++;
      logEv('devtools_attempt', combo);
      console.log('[PsySense] Suspicious key blocked:', combo);
      showToast('Developer tools are disabled during the interview');
      updateRiskScore();
      syncStateToStreamlit();
    }}
  }};
 
  // 8) Dismiss button click
  var onDismiss = function() {{
    var ov = doc.getElementById('ps-proctor-overlay');
    if (ov) {{ ov.className = ''; ov.style.display = 'none'; }}
    S._dismissCooldown = Date.now();
    S.tabLeftAt = null;
    console.log('[PsySense] Overlay dismissed');
  }};
 
  // 9) Fullscreen change detection
  var onFsc = function() {{
    if (!S.isInterviewActive) return;
    var fsEl = doc.fullscreenElement || doc.webkitFullscreenElement || doc.msFullscreenElement;
    if (!fsEl && S._fullscreenActive) {{
      S.fullscreenExits++;
      S._fullscreenActive = false;
      logEv('fullscreen_exit', 'Exit #' + S.fullscreenExits);
      console.log('[PsySense] Fullscreen EXIT #' + S.fullscreenExits);
      var fsOv = doc.getElementById('ps-fullscreen-overlay');
      if (fsOv) {{ fsOv.style.display = 'flex'; fsOv.className = 'ps-active'; }}
      updateRiskScore();
      syncStateToStreamlit();
    }} else if (fsEl) {{
      S._fullscreenActive = true;
      var fsOv = doc.getElementById('ps-fullscreen-overlay');
      if (fsOv) {{ fsOv.className = ''; fsOv.style.display = 'none'; }}
      console.log('[PsySense] Fullscreen entered');
    }}
  }};
 
  // 10) Fullscreen re-enter button
  var onFsReenter = function() {{
    try {{
      var el = doc.documentElement;
      var rfs = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
      if (rfs) rfs.call(el);
    }} catch(e) {{ console.warn('[PsySense] Fullscreen request failed:', e); }}
  }};

  // ↓ ADD HERE
  var onMouseLeave = function() {{
    if (!S.isInterviewActive) return;
    if (!S.tabLeftAt) S.tabLeftAt = Date.now();
  }};
  var onMouseEnter = function() {{
    if (!S.isInterviewActive || !S.tabLeftAt) return;
    if (Date.now() - S._dismissCooldown < 1000) {{ S.tabLeftAt = null; return; }}
    var away = Date.now() - S.tabLeftAt;
    S.tabLeftAt = null;
    if (away > 500 && !doc.hidden) handleSwitch('window_switch', away);
  }};

  // ── Risk score calculator ──
  function updateRiskScore() {{
    S.riskScore = (S.tabSwitches * 2) + (S.pasteAttempts * 5) +
                  (S.fullscreenExits * 4) + (S.devToolsAttempts * 8);
    var badge = doc.getElementById('ps-risk-badge');
    if (badge) {{
      if (S.riskScore === 0) badge.textContent = '';
      else if (S.riskScore < 10) badge.textContent = '| Risk: Low';
      else if (S.riskScore < 25) {{ badge.textContent = '| Risk: Medium'; badge.style.color = '#f97316'; }}
      else {{ badge.textContent = '| Risk: High'; badge.style.color = '#ef4444'; }}
    }}
  }}
 
  // ── Show/hide secure banner ──
  var banner = doc.getElementById('ps-secure-banner');
  if (banner) {{
    if (S.isInterviewActive) banner.className = 'ps-active';
    else {{ banner.className = ''; banner.style.display = 'none'; }}
  }}
 
  // ── Attach all listeners ──
  doc.addEventListener('visibilitychange', onVis);
  win.addEventListener('blur', onBlur);
  win.addEventListener('focus', onFocus);
  doc.addEventListener('paste', onPaste, true);
  doc.addEventListener('copy', onCopy, true);
  doc.addEventListener('contextmenu', onCtx);
  doc.addEventListener('keydown', onKey, true);
  doc.addEventListener('fullscreenchange', onFsc);
  doc.addEventListener('webkitfullscreenchange', onFsc);   // Safari / older Chrome
  doc.addEventListener('msfullscreenchange', onFsc);        // Edge legacy
  doc.addEventListener('mouseleave', onMouseLeave);   // ← ADD
  doc.addEventListener('mouseenter', onMouseEnter);
  var dismissBtn = doc.getElementById('ps-proctor-dismiss');
  if (dismissBtn) {{
    dismissBtn.addEventListener('click', onDismiss);
    console.log('[PsySense] Dismiss button handler attached');
  }}
 
  var fsBtn = doc.getElementById('ps-fs-reenter');
  if (fsBtn) {{
    fsBtn.addEventListener('click', onFsReenter);
    console.log('[PsySense] Fullscreen re-enter button attached');
  }}
 
  win.__psL = {{ vis: onVis, blur: onBlur, focus: onFocus,
                paste: onPaste, copy: onCopy, ctx: onCtx, key: onKey,
                fsc: onFsc, dismiss: onDismiss, dismissBtn: dismissBtn,
                fsReenter: onFsReenter, fsBtn: fsBtn,
                mouseLeave: onMouseLeave, mouseEnter: onMouseEnter  }};
 
  win.__psActivateProctoring = function() {{
    S.isInterviewActive = true;
    try {{ if (win.screen && win.screen.isExtended !== undefined) S.screenCount = win.screen.isExtended ? 2 : 1; }} catch(e) {{}}
    logEv('proctoring_activated', 'screens:' + S.screenCount);
    var b = doc.getElementById('ps-secure-banner');
    if (b) b.className = 'ps-active';
    console.log('[PsySense] Proctoring activated');
  }};
  win.__psDeactivateProctoring = function() {{
    S.isInterviewActive = false;
    var b = doc.getElementById('ps-secure-banner');
    if (b) {{ b.className = ''; b.style.display = 'none'; }}
  }};
  win.__psGetProctoringState = function() {{ return JSON.stringify(S); }};
  win.__psEnterFullscreen = function() {{
    try {{
      var el = doc.documentElement;
      var rfs = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
      if (rfs) {{ rfs.call(el); S._fullscreenActive = true; }}
    }} catch(e) {{}}
  }};
 
  updateRiskScore();
  syncStateToStreamlit();
  if (win.__psSyncTimer) win.clearInterval(win.__psSyncTimer);
  win.__psSyncTimer = win.setInterval(syncStateToStreamlit, 2000);
  console.log('[PsySense] Listeners attached. Active:', S.isInterviewActive);
}})();
</script>
"""
 
 
# ─────────────────────────────────────────────────────────
# Public API: called from demo_app.py
# ─────────────────────────────────────────────────────────
 
def inject_proctoring_ui():
    """Inject the proctoring CSS + HTML overlay into the page.
    Call this once near the top of the app, after global styles."""
    st.markdown(_PROCTORING_CSS_HTML, unsafe_allow_html=True)
 
 
def inject_proctoring_js():
    """Inject the proctoring JavaScript engine.
    Automatically detects the current phase and activates if in interview.
    Must be called after inject_proctoring_ui()."""
    phase = st.session_state.get("phase", "start")
    is_active = phase in (
        "prep", "recording", "processing", "transcript"
    )
    reset_state = phase in ("start", "camera_setup")
    components.html(_build_proctoring_js(is_active, reset_state), height=0, scrolling=False)
def inject_fullscreen_gate():
    """
    Renders a fullscreen-request modal over the page.
    Call once when entering camera_setup phase.
    The button triggers fullscreen from a real user gesture (browser requirement).
    """
    st.markdown("""
<div id="ps-fs-gate" style="display:flex; position:fixed; inset:0; z-index:1000000;
     background:rgba(13,13,20,0.85); backdrop-filter:blur(10px);
     justify-content:center; align-items:center; font-family:'DM Sans',sans-serif">
  <div style="background:#fff; border-radius:18px; padding:40px 48px; max-width:480px;
       width:90%; text-align:center; box-shadow:0 20px 60px rgba(0,0,0,0.4)">
    <div style="font-size:40px; margin-bottom:16px">&#x1F512;</div>
    <h2 style="font-size:20px; font-weight:700; margin:0 0 10px; color:#0f0f1e">
      Secure Interview Mode</h2>
    <p style="font-size:14px; color:#555; line-height:1.7; margin:0 0 24px">
      This interview uses fullscreen mode and records integrity signals such as
      window changes, paste attempts, and additional faces for recruiter review.</p>
    <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-bottom:20px">
      <span style="background:#effaf4; color:#166534; border:1px solid #b6f0cc;
           border-radius:8px; padding:6px 14px; font-size:13px; font-weight:600">
        &#10003; Camera</span>
      <span style="background:#effaf4; color:#166534; border:1px solid #b6f0cc;
           border-radius:8px; padding:6px 14px; font-size:13px; font-weight:600">
        &#10003; Microphone</span>
      <span style="background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe;
           border-radius:8px; padding:6px 14px; font-size:13px; font-weight:600">
        &#x2B1B; Fullscreen (required)</span>
    </div>
    <button id="ps-fs-gate-btn"
      style="background:#1a1a2e; color:#fff; border:none; border-radius:12px;
             padding:14px 32px; font-size:15px; font-weight:700; cursor:pointer;
             width:100%; font-family:'DM Sans',sans-serif; letter-spacing:-0.2px">
      Continue to Interview &#8594;
    </button>
    <p id="ps-fs-gate-err"
       style="color:#dc2626; font-size:13px; margin:12px 0 0; display:none">
      Fullscreen is required. Please allow it to continue.
    </p>
  </div>
</div>
""", unsafe_allow_html=True)
    components.html("""
<script>
(function() {
  var win = window.parent || window;
  var doc = win.document;
  var gate = doc.getElementById('ps-fs-gate');
  var btn  = doc.getElementById('ps-fs-gate-btn');
  var err  = doc.getElementById('ps-fs-gate-err');
  if (!gate) return;
  gate.style.display = 'flex';
  btn.addEventListener('click', function() {
    var el  = doc.documentElement;
    var rfs = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
    if (!rfs) {
      gate.style.display = 'none';
      return;
    }
    rfs.call(el).then(function() {
      gate.style.display = 'none';
      if (win.__psProctoring) win.__psProctoring._fullscreenActive = true;
      if (win.__psActivateProctoring) win.__psActivateProctoring();
    }).catch(function() {
      if (err) err.style.display = 'block';
    });
  });
})();
</script>
""", height=0, scrolling=False)
 
 
def render_proctoring_chips(tab_sw: int | None = None, mf: int | None = None) -> str:
    """
    Render the proctoring status chips for the camera panel.
 
    FIX: The original version read counters from st.session_state, which are
    never written by JS (the JS state lives in window.__psProctoring on the
    parent frame).  Those values were therefore always 0.
 
    Callers should pass live counters synced via sync_proctoring_state_from_js()
    or a Streamlit component callback.  Falls back to session_state so existing
    call-sites continue to work if callers haven't been updated yet.
 
    Returns the HTML string for use inside st.markdown().
    """
    if tab_sw is None:
        tab_sw = st.session_state.get("proctoring_tab_switches", 0)
    if mf is None:
        mf = st.session_state.get("proctoring_multi_face_total", 0)
 
    tab_cls = "ps-chip-ok" if tab_sw == 0 else ("ps-chip-warn" if tab_sw < 3 else "ps-chip-bad")
    face_cls = "ps-chip-ok" if mf == 0 else "ps-chip-bad"
 
    return f"""<div class="ps-proctor-chips">
      <span class="ps-proctor-chip {tab_cls}">Tab: {tab_sw}</span>
      <span class="ps-proctor-chip {face_cls}">Faces: {mf}</span>
      <span class="ps-proctor-chip ps-chip-ok">Proctored</span>
    </div>"""
 
 
def _coerce_query_param(value):
    if isinstance(value, list):
        return value[-1] if value else None
    return value


def _query_payload() -> str | None:
    try:
        return _coerce_query_param(st.query_params.get("ps_proctor_payload"))
    except Exception:
        return None


def sync_proctoring_state_from_query_params() -> None:
    """Read the compact browser proctoring payload from st.query_params."""
    sync_proctoring_state_from_js(_query_payload())


def sync_proctoring_state_from_js(raw_json: str | None) -> None:
    """
    Write JS proctoring counters into st.session_state so Python code
    (render_proctoring_chips, build_proctoring_summary) sees live values.
 
    Call this in your Streamlit component callback that receives the JSON
    string returned by window.__psGetProctoringState() on the client.
 
    Example (in demo_app.py):
        state_json = st.session_state.get("ps_proctor_payload")
        sync_proctoring_state_from_js(state_json)
    """
    if not raw_json:
        return
    try:
        data = json.loads(raw_json)
    except (ValueError, TypeError):
        try:
            data = json.loads(unquote(raw_json))
        except (ValueError, TypeError):
            return
 
    st.session_state["proctoring_tab_switches"]    = data.get("tabSwitches", 0)
    st.session_state["proctoring_paste_attempts"]  = data.get("pasteAttempts", 0)
    st.session_state["proctoring_fullscreen_exits"]= data.get("fullscreenExits", 0)
    st.session_state["proctoring_devtools_attempts"]= data.get("devToolsAttempts", 0)
    st.session_state["proctoring_screen_count"]    = data.get("screenCount", 1)
    st.session_state["proctoring_events"]          = data.get("events", [])
 
 
def build_proctoring_summary() -> dict:
    """Collect proctoring counters from session state into a summary dict
    for saving to the database.
    Call sync_proctoring_state_from_js() before this to ensure values are current."""
    sync_proctoring_state_from_query_params()

    tab_sw = st.session_state.get("proctoring_tab_switches", 0)
    paste  = st.session_state.get("proctoring_paste_attempts", 0)
    fs_ex  = st.session_state.get("proctoring_fullscreen_exits", 0)
    mf     = st.session_state.get("proctoring_multi_face_total", 0)
    scrn   = st.session_state.get("proctoring_screen_count", 1)
    devt   = st.session_state.get("proctoring_devtools_attempts", 0)
    events = st.session_state.get("proctoring_events", [])
 
    # Weighted risk scoring (same weights as proctoring.py and client JS)
    risk_score = (
        (tab_sw * 2) + (paste * 5) + (fs_ex * 4) +
        (mf * 6) + (devt * 8) + (max(0, scrn - 1) * 3)
    )
 
    if risk_score >= 40:
        risk = "Critical"
    elif risk_score >= 25:
        risk = "High"
    elif risk_score >= 10:
        risk = "Medium"
    else:
        risk = "Low"
 
    flags = []
    if tab_sw > 0:
        flags.append(f"Tab switched {tab_sw} time(s)")
    if paste > 0:
        flags.append(f"Paste attempted {paste} time(s)")
    if fs_ex > 0:
        flags.append(f"Fullscreen exited {fs_ex} time(s)")
    if mf > 0:
        flags.append(f"Multi-face detected {mf} time(s)")
    if devt > 0:
        flags.append(f"DevTools attempted {devt} time(s)")
    if scrn > 1:
        flags.append(f"Multi-screen detected ({scrn} screens)")
 
    return {
        "tab_switch_count":        tab_sw,
        "paste_attempt_count":     paste,
        "fullscreen_exit_count":   fs_ex,
        "multi_face_count":        mf,
        "devtools_attempt_count":  devt,
        "screen_count":            scrn,
        "risk_score":              risk_score,
        "risk_level":              risk,
        "flags":                   flags,
        "events":                  events,
    }
