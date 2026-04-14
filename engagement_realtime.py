"""
engagement_realtime.py
----------------------
Real-time engagement detector using OpenCV only.
No mediapipe — zero protobuf conflict with tensorflow.

Tracks:
- Face presence (is face visible)
- Eye contact (are eyes detected and centered)
- Head stability (face not moving excessively)
- Engagement score 0-10
"""

import cv2
import numpy as np
import threading
import os
from collections import deque


# ── Deployment-safe cascade loading ──────────────────────────────────────
# On some Linux servers cv2.data.haarcascades is an empty string or the
# XML files are missing even though opencv-python is installed.
# We try three locations in order and raise a clear error if none work.

def _load_cascade(filename: str) -> cv2.CascadeClassifier:
    candidates = [
        # 1. Standard opencv-python pip install (works locally + most servers)
        os.path.join(cv2.data.haarcascades, filename),
        # 2. System OpenCV installed via apt on Ubuntu/Debian
        f"/usr/share/opencv4/haarcascades/{filename}",
        f"/usr/share/opencv/haarcascades/{filename}",
        # 3. Conda environment
        os.path.join(os.path.dirname(cv2.__file__), "data", filename),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            clf = cv2.CascadeClassifier(path)
            if not clf.empty():
                return clf
    # Last resort — let OpenCV try its default resolution
    clf = cv2.CascadeClassifier(filename)
    if clf.empty():
        raise RuntimeError(
            f"Could not load Haar cascade '{filename}'. "
            f"Tried: {candidates}. "
            f"Install opencv-python via pip (not apt) to fix this."
        )
    return clf


_face_cascade = _load_cascade("haarcascade_frontalface_default.xml")
_eye_cascade  = _load_cascade("haarcascade_eye.xml")

_NEUTRAL_EMOTION = {"dominant": "neutral", "breakdown": {}}


class EngagementDetector:

    _WINDOW          = 150
    _SAMPLE_INTERVAL = 90
    _ABSENCE_WARN    = 3
    _ABSENCE_FLAG    = 0.30

    def __init__(self):
        self._lock = threading.Lock()
        self._countdown_value = None
        self._face_present   = deque(maxlen=self._WINDOW)
        self._gaze_ok        = deque(maxlen=self._WINDOW)
        self._face_positions = deque(maxlen=self._WINDOW)

        self._total_frames       = 0
        self._absent_frames      = 0
        self._consecutive_absent = 0

        self._score_samples = []
        self._frame_count   = 0

    def process_frame(self, bgr_frame: np.ndarray) -> np.ndarray:
        h, w      = bgr_frame.shape[:2]
        annotated = bgr_frame.copy()
        gray      = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)

        # Detect faces
        faces = _face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=7, minSize=(80, 80)
        )

        with self._lock:
            self._total_frames += 1
            self._frame_count  += 1

            if len(faces) > 0:
                # Use largest face
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])

                self._consecutive_absent = 0
                self._face_present.append(1)

                # Face center position (normalized 0-1)
                face_cx = (x + fw / 2) / w
                face_cy = (y + fh / 2) / h
                self._face_positions.append((face_cx, face_cy))

                # Gaze — is face centered horizontally
                gaze_ok = 0.30 < face_cx < 0.70
                self._gaze_ok.append(int(gaze_ok))

                # Detect eyes inside face region
                face_roi = gray[y:y+fh, x:x+fw]
                eyes = _eye_cascade.detectMultiScale(
                    face_roi, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20)
                )
                eyes_visible = len(eyes) >= 1

                # Draw face box
                box_color = (0, 200, 100) if gaze_ok else (0, 165, 255)
                cv2.rectangle(annotated, (x, y), (x+fw, y+fh), box_color, 2)

                # Draw eye dots
                for (ex, ey, ew, eh) in eyes[:2]:
                    eye_cx = x + ex + ew // 2
                    eye_cy = y + ey + eh // 2
                    cv2.circle(annotated, (eye_cx, eye_cy), 4, (255, 200, 0), -1)

                # Draw face center dot
                cv2.circle(annotated, (int(face_cx * w), int(face_cy * h)), 5, (0, 255, 255), -1)

                annotated = self._draw_hud(annotated, w, h, gaze_ok, eyes_visible)

            else:
                self._absent_frames      += 1
                self._consecutive_absent += 1
                self._face_present.append(0)
                self._gaze_ok.append(0)
                self._face_positions.append((0.5, 0.5))

                if self._consecutive_absent >= self._ABSENCE_WARN:
                    cv2.rectangle(annotated, (0, 0), (w, h), (0, 0, 180), 3)
                    cv2.rectangle(annotated, (w//2 - 160, h//2 - 30),
                                  (w//2 + 160, h//2 + 30), (20, 20, 20), -1)
                    cv2.putText(annotated, "Face not visible!",
                                (w//2 - 120, h//2 + 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 60, 220), 2)

                annotated = self._draw_hud(annotated, w, h, False, False)

            if self._frame_count % self._SAMPLE_INTERVAL == 0:
                s = self._compute_score()
                # Only record samples when we have meaningful data (at least 30 frames)
                if self._total_frames >= 30:
                    self._score_samples.append(s)

        return annotated

    def get_score(self) -> float:
        with self._lock:
            return self._compute_score()

    def get_avg_score(self) -> float:
        with self._lock:
            if not self._score_samples:
                return self._compute_score()
            return round(float(np.mean(self._score_samples)), 2)

    def get_absence_ratio(self) -> float:
        with self._lock:
            if self._total_frames == 0:
                return 0.0
            return round(self._absent_frames / self._total_frames, 3)

    def is_low_presence(self) -> bool:
        return self.get_absence_ratio() > self._ABSENCE_FLAG

    def get_emotion_summary(self) -> dict:
        return dict(_NEUTRAL_EMOTION)

    def reset_session(self):
        with self._lock:
            self._face_present.clear()
            self._gaze_ok.clear()
            self._face_positions.clear()
            self._total_frames       = 0
            self._absent_frames      = 0
            self._consecutive_absent = 0
            self._score_samples      = []
            self._frame_count        = 0

    def set_countdown(self, value):
        """Set countdown number to display on camera feed."""
        with self._lock:
            self._countdown_value = value

    def snapshot_and_reset(self):
        with self._lock:
            if self._score_samples:
                # Trim extreme low outliers caused by brief camera occlusion
                trimmed = sorted(self._score_samples)
                cut = max(1, len(trimmed) // 5)   # drop bottom 20%
                kept = trimmed[cut:] if cut < len(trimmed) else trimmed
                score = round(float(np.mean(kept)), 2)
            else:
                score = self._compute_score()
            # Never return 0 from a snapshot — minimum neutral score
            score = max(score, 1.0)
            absent = (round(self._absent_frames / self._total_frames, 3)
                      if self._total_frames > 0 else 0.0)
            emotion = dict(_NEUTRAL_EMOTION)

            # Reset inline so nothing changes between reads
            self._face_present.clear()
            self._gaze_ok.clear()
            self._face_positions.clear()
            self._total_frames       = 0
            self._absent_frames      = 0
            self._consecutive_absent = 0
            self._score_samples      = []
            self._frame_count        = 0
            self._countdown_value    = None

        return score, absent, emotion

    def _compute_score(self) -> float:
        n = len(self._face_present)
        if n == 0:
            return 5.0

        face_presence  = sum(self._face_present) / n
        gaze_stability = sum(self._gaze_ok) / n

        positions = list(self._face_positions)
        if len(positions) >= 2:
            displacements = [
                np.sqrt((positions[i][0] - positions[i-1][0])**2 +
                        (positions[i][1] - positions[i-1][1])**2)
                for i in range(1, len(positions))
            ]
            avg_disp = float(np.mean(displacements))
            stability = max(0.0, 1.0 - (avg_disp / 0.02))
        else:
            stability = 1.0

        raw = (
            0.5 * face_presence
            + 0.3 * gaze_stability
            + 0.2 * stability
        )

        score = min(raw * 10, 10.0)
        if face_presence >= 0.70:
            score = max(score, 4.0)
        elif face_presence >= 0.50:
            score = max(score, 2.5)

        return round(score, 2)

    def _draw_hud(self, frame, w, h, gaze_ok, eyes_visible):
        # Call _compute_score() directly — already inside lock from process_frame()
        score       = self._compute_score()
        absence_pct = (self._absent_frames / max(self._total_frames, 1)) * 100

        color = (0, 200, 100) if score >= 7 else (0, 165, 255) if score >= 4 else (0, 60, 220)

        # Score badge top-left
        cv2.rectangle(frame, (10, 10), (240, 70), (20, 20, 20), -1)
        cv2.rectangle(frame, (10, 10), (240, 70), color, 1)
        cv2.putText(frame, f"Engagement: {score}/10",
                    (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.60, color, 2)
        cv2.putText(frame, f"Face absent: {absence_pct:.0f}%",
                    (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                    (0, 60, 200) if absence_pct > 30 else (160, 160, 160), 1)

        # Gaze dot top-right
        dot_color = (0, 220, 80) if gaze_ok else (0, 60, 220)
        cv2.circle(frame, (w - 28, 28), 11, dot_color, -1)
        cv2.putText(frame, "ON" if gaze_ok else "OFF",
                    (w - 58, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.42, dot_color, 1)

        # Eyes indicator
        eye_color = (0, 220, 80) if eyes_visible else (0, 60, 220)
        cv2.putText(frame, f"Eyes: {'detected' if eyes_visible else 'not detected'}",
                    (18, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.40, eye_color, 1)

        # Countdown overlay
        if self._countdown_value is not None and self._countdown_value > 0:
            overlay = frame.copy()
            cv2.rectangle(overlay, (w//2 - 80, h//2 - 70),
                         (w//2 + 80, h//2 + 50), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

            cv2.putText(
                frame, "GET READY",
                (w//2 - 60, h//2 - 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (200, 200, 200),
                1
            )
            num_str  = str(self._countdown_value)
            x_offset = w//2 - 22 if self._countdown_value >= 10 else w//2 - 14
            cv2.putText(
                frame,
                num_str,
                (x_offset, h//2 + 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                2.8,
                (255, 255, 255),
                4
            )
        return frame


# Standalone blocking version
def compute_engagement_score(duration: int = 10) -> float:
    import time
    cap      = cv2.VideoCapture(0)
    detector = EngagementDetector()
    start    = time.time()

    while time.time() - start < duration:
        ret, frame = cap.read()
        if not ret:
            continue
        annotated = detector.process_frame(frame)
        cv2.imshow("Engagement Detection", annotated)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    return detector.get_avg_score()