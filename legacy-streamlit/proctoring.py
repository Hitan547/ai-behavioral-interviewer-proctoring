"""
proctoring.py
-------------
Server-side proctoring session manager for PsySense anti-cheating.
 
Tracks:
- Tab switches (with progressive warning levels)
- Copy-paste attempts
- Fullscreen exits
- Multiple face detections
- Secondary screen count
- DevTools open attempts          ← FIX: was in RISK_WEIGHTS but never tracked
 
All events are timestamped and associated with the current question index.
The recruiter sees a summary + risk level on the dashboard.
 
Fix log:
  - Added devtools_attempt_count attribute (was in RISK_WEIGHTS but never
    incremented, never stored, never reset — dead weight in the score).
  - Added record_devtools_attempt() method.
  - get_risk_score() now includes devtools_attempt_count * weight 8.
  - get_flags() surfaces devtools attempts to recruiter.
  - get_summary() includes devtools_attempt_count.
  - reset() clears devtools_attempt_count.
"""
 
import time
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional
 
 
@dataclass
class ProctoringEvent:
    """A single proctoring event."""
    event_type: str          # tab_switch, paste_attempt, fullscreen_exit, multi_face, screen_check
    timestamp: float         # time.time()
    question_index: int = 0  # which question was active
    duration: float = 0.0    # for tab_switch: seconds away
    details: str = ""        # extra info
 
 
class ProctoringSession:
    """
    Manages all proctoring state for one interview session.
    Thread-safe — can be updated from JS callbacks and video processor.
    """
 
    # Progressive warning thresholds for tab switches
    TAB_WARN_YELLOW = 1   # 1st switch → yellow toast
    TAB_WARN_ORANGE = 2   # 2nd switch → orange overlay
    TAB_WARN_RED    = 3   # 3rd+ → red overlay + timer pause
 
    def __init__(self):
        self._lock = threading.RLock()
        self._events: List[ProctoringEvent] = []
 
        # Counters
        self.tab_switch_count: int = 0
        self.paste_attempt_count: int = 0
        self.fullscreen_exit_count: int = 0
        self.multi_face_count: int = 0
        self.screen_count: int = 1          # default 1 monitor
        self.devtools_attempt_count: int = 0  # FIX: was missing entirely
 
        # Tab switch tracking
        self._tab_left_at: Optional[float] = None
        self._total_time_away: float = 0.0
 
    # ── Tab Switch ────────────────────────────────────────────────────────
 
    def record_tab_leave(self, question_index: int = 0):
        """Called when candidate leaves the tab."""
        with self._lock:
            self._tab_left_at = time.time()
 
    def record_tab_return(self, question_index: int = 0) -> dict:
        """
        Called when candidate returns to tab.
        Returns warning level info for the UI.
        """
        with self._lock:
            duration = 0.0
            if self._tab_left_at:
                duration = round(time.time() - self._tab_left_at, 1)
                self._total_time_away += duration
                self._tab_left_at = None
 
            self.tab_switch_count += 1
            self._events.append(ProctoringEvent(
                event_type="tab_switch",
                timestamp=time.time(),
                question_index=question_index,
                duration=duration,
                details=f"Away for {duration}s",
            ))
 
            count = self.tab_switch_count
            if count >= self.TAB_WARN_RED:
                level = "red"
            elif count >= self.TAB_WARN_ORANGE:
                level = "orange"
            else:
                level = "yellow"
 
            return {
                "level": level,
                "count": count,
                "duration": duration,
                "total_time_away": round(self._total_time_away, 1),
            }
 
    # ── Copy-Paste ────────────────────────────────────────────────────────
 
    def record_paste_attempt(self, question_index: int = 0):
        """Called when candidate tries to paste."""
        with self._lock:
            self.paste_attempt_count += 1
            self._events.append(ProctoringEvent(
                event_type="paste_attempt",
                timestamp=time.time(),
                question_index=question_index,
                details="Paste blocked",
            ))
 
    def record_copy_attempt(self, question_index: int = 0):
        """Called when candidate tries to copy question text."""
        with self._lock:
            self._events.append(ProctoringEvent(
                event_type="copy_attempt",
                timestamp=time.time(),
                question_index=question_index,
                details="Copy blocked",
            ))
 
    # ── Fullscreen ────────────────────────────────────────────────────────
 
    def record_fullscreen_exit(self, question_index: int = 0):
        """Called when candidate exits fullscreen."""
        with self._lock:
            self.fullscreen_exit_count += 1
            self._events.append(ProctoringEvent(
                event_type="fullscreen_exit",
                timestamp=time.time(),
                question_index=question_index,
                details="Exited fullscreen",
            ))
 
    # ── Multi-Face ────────────────────────────────────────────────────────
 
    def record_multi_face(self, question_index: int = 0, face_count: int = 2):
        """Called when multiple faces detected on camera."""
        with self._lock:
            self.multi_face_count += 1
            self._events.append(ProctoringEvent(
                event_type="multi_face",
                timestamp=time.time(),
                question_index=question_index,
                details=f"{face_count} faces detected",
            ))
 
    # ── DevTools ──────────────────────────────────────────────────────────
    # FIX: this method and the counter were entirely missing. The weight-8
    # entry in RISK_WEIGHTS existed but was never used in get_risk_score().
 
    def record_devtools_attempt(self, question_index: int = 0, key_combo: str = ""):
        """Called when candidate tries to open browser DevTools (F12, Ctrl+Shift+I, etc.)."""
        with self._lock:
            self.devtools_attempt_count += 1
            self._events.append(ProctoringEvent(
                event_type="devtools_attempt",
                timestamp=time.time(),
                question_index=question_index,
                details=f"Blocked: {key_combo}" if key_combo else "DevTools shortcut blocked",
            ))
 
    # ── Screen Detection ──────────────────────────────────────────────────
 
    def set_screen_count(self, count: int):
        """Set detected monitor count (called once at interview start)."""
        with self._lock:
            self.screen_count = count
            if count > 1:
                self._events.append(ProctoringEvent(
                    event_type="screen_check",
                    timestamp=time.time(),
                    details=f"{count} monitors detected",
                ))
 
    # ── Risk Assessment ───────────────────────────────────────────────────
 
    # Weighted risk scoring (matches client-side JS weights in proctoring_client.py)
    RISK_WEIGHTS = {
        "tab_switch": 2,
        "paste_attempt": 5,
        "copy_attempt": 3,
        "fullscreen_exit": 4,
        "multi_face": 6,
        "devtools_attempt": 8,   # FIX: was defined but never applied
        "screen_extra": 3,       # per extra screen beyond 1
    }
    RISK_THRESHOLD_MEDIUM   = 10
    RISK_THRESHOLD_HIGH     = 25
    RISK_THRESHOLD_CRITICAL = 40
 
    def get_risk_score(self) -> int:
        """Calculate numeric risk score based on weighted events."""
        with self._lock:
            score = 0
            score += self.tab_switch_count       * self.RISK_WEIGHTS["tab_switch"]
            score += self.paste_attempt_count    * self.RISK_WEIGHTS["paste_attempt"]
            score += self.fullscreen_exit_count  * self.RISK_WEIGHTS["fullscreen_exit"]
            score += self.multi_face_count       * self.RISK_WEIGHTS["multi_face"]
            score += self.devtools_attempt_count * self.RISK_WEIGHTS["devtools_attempt"]  # FIX: was missing
            score += max(0, self.screen_count - 1) * self.RISK_WEIGHTS["screen_extra"]
            return score
 
    def get_risk_level(self) -> str:
        """
        Calculate overall proctoring risk level from weighted score.
 
        Low:      0-9   score
        Medium:   10-24 score
        High:     25-39 score
        Critical: 40+   score (auto-terminate threshold)
        """
        score = self.get_risk_score()
        if score >= self.RISK_THRESHOLD_CRITICAL:
            return "Critical"
        if score >= self.RISK_THRESHOLD_HIGH:
            return "High"
        if score >= self.RISK_THRESHOLD_MEDIUM:
            return "Medium"
        return "Low"
 
    def get_flags(self) -> List[str]:
        """Return human-readable flag messages for the recruiter."""
        with self._lock:
            flags = []
            if self.tab_switch_count > 0:
                flags.append(
                    f"Tab switched {self.tab_switch_count} time(s), "
                    f"total {round(self._total_time_away, 1)}s away"
                )
            if self.paste_attempt_count > 0:
                flags.append(
                    f"Attempted to paste {self.paste_attempt_count} time(s)"
                )
            if self.fullscreen_exit_count > 0:
                flags.append(
                    f"Exited fullscreen {self.fullscreen_exit_count} time(s)"
                )
            if self.multi_face_count > 0:
                flags.append(
                    f"Multiple faces detected {self.multi_face_count} time(s)"
                )
            if self.devtools_attempt_count > 0:          # FIX: was missing
                flags.append(
                    f"Attempted to open DevTools {self.devtools_attempt_count} time(s)"
                )
            if self.screen_count > 1:
                flags.append(
                    f"{self.screen_count} monitors detected"
                )
            return flags
 
    def get_tab_switch_warning_level(self) -> str:
        """Current warning level based on tab switch count."""
        with self._lock:
            if self.tab_switch_count >= self.TAB_WARN_RED:
                return "red"
            elif self.tab_switch_count >= self.TAB_WARN_ORANGE:
                return "orange"
            elif self.tab_switch_count >= self.TAB_WARN_YELLOW:
                return "yellow"
            return "none"
 
    # ── Serialization ─────────────────────────────────────────────────────
 
    def get_summary(self) -> dict:
        """
        Return a JSON-serializable summary for database storage.
        This is saved to CandidateSession.proctoring_json.
        """
        with self._lock:
            # Per-question breakdown of tab switches
            per_question_tabs: Dict[int, Dict] = {}
            for e in self._events:
                if e.event_type == "tab_switch":
                    qi = e.question_index
                    if qi not in per_question_tabs:
                        per_question_tabs[qi] = {"count": 0, "total_away": 0.0}
                    per_question_tabs[qi]["count"] += 1
                    per_question_tabs[qi]["total_away"] += e.duration
 
            return {
                "risk_level": self.get_risk_level(),
                "risk_score": self.get_risk_score(),
                "tab_switch_count": self.tab_switch_count,
                "total_time_away": round(self._total_time_away, 1),
                "paste_attempt_count": self.paste_attempt_count,
                "fullscreen_exit_count": self.fullscreen_exit_count,
                "multi_face_count": self.multi_face_count,
                "devtools_attempt_count": self.devtools_attempt_count,  # FIX: was missing
                "screen_count": self.screen_count,
                "flags": self.get_flags(),
                "per_question_tabs": {str(k): v for k, v in per_question_tabs.items()},
                "events": [
                    {
                        "type": e.event_type,
                        "timestamp": e.timestamp,
                        "question": e.question_index,
                        "duration": e.duration,
                        "details": e.details,
                    }
                    for e in self._events
                ],
            }
 
    def reset(self):
        """Clear all proctoring data (for new interview)."""
        with self._lock:
            self._events.clear()
            self.tab_switch_count = 0
            self.paste_attempt_count = 0
            self.fullscreen_exit_count = 0
            self.multi_face_count = 0
            self.devtools_attempt_count = 0   # FIX: was missing from reset
            self.screen_count = 1
            self._tab_left_at = None
            self._total_time_away = 0.0
 
