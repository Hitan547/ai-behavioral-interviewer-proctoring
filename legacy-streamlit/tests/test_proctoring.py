"""
tests/test_proctoring.py
------------------------
Tests for the server-side proctoring session manager.
"""

import pytest
import threading
from proctoring import ProctoringSession


@pytest.fixture
def session():
    return ProctoringSession()


# ── Tab Switch Tracking ──────────────────────────────────────────────────


class TestTabSwitching:
    def test_single_tab_switch(self, session):
        session.record_tab_leave(question_index=0)
        result = session.record_tab_return(question_index=0)
        assert result["count"] == 1
        assert result["level"] == "yellow"
        assert session.tab_switch_count == 1

    def test_progressive_warnings(self, session):
        # 1st switch → yellow
        session.record_tab_leave()
        r1 = session.record_tab_return()
        assert r1["level"] == "yellow"

        # 2nd switch → orange
        session.record_tab_leave()
        r2 = session.record_tab_return()
        assert r2["level"] == "orange"

        # 3rd switch → red
        session.record_tab_leave()
        r3 = session.record_tab_return()
        assert r3["level"] == "red"

    def test_total_time_away_accumulates(self, session):
        import time

        session.record_tab_leave()
        time.sleep(0.1)
        r = session.record_tab_return()
        assert r["total_time_away"] > 0


# ── Event Recording ─────────────────────────────────────────────────────


class TestEventRecording:
    def test_paste_attempt(self, session):
        session.record_paste_attempt(question_index=1)
        assert session.paste_attempt_count == 1

    def test_copy_attempt(self, session):
        session.record_copy_attempt(question_index=0)
        # Copy attempt doesn't increment paste_attempt_count
        assert session.paste_attempt_count == 0

    def test_fullscreen_exit(self, session):
        session.record_fullscreen_exit(question_index=2)
        assert session.fullscreen_exit_count == 1

    def test_multi_face(self, session):
        session.record_multi_face(question_index=0, face_count=3)
        assert session.multi_face_count == 1

    def test_devtools_attempt(self, session):
        session.record_devtools_attempt(question_index=0, key_combo="F12")
        assert session.devtools_attempt_count == 1

    def test_screen_count(self, session):
        session.set_screen_count(2)
        assert session.screen_count == 2


# ── Risk Scoring ─────────────────────────────────────────────────────────


class TestRiskScoring:
    def test_clean_session_is_low(self, session):
        assert session.get_risk_score() == 0
        assert session.get_risk_level() == "Low"

    def test_risk_weights_applied(self, session):
        session.record_paste_attempt()  # weight 5
        assert session.get_risk_score() == 5

    def test_medium_threshold(self, session):
        # 5 tab switches × 2 = 10 → Medium
        for _ in range(5):
            session.record_tab_leave()
            session.record_tab_return()
        assert session.get_risk_level() == "Medium"

    def test_high_threshold(self, session):
        # 5 paste attempts × 5 = 25 → High
        for _ in range(5):
            session.record_paste_attempt()
        assert session.get_risk_level() == "High"

    def test_critical_threshold(self, session):
        # 5 devtools × 8 = 40 → Critical
        for _ in range(5):
            session.record_devtools_attempt()
        assert session.get_risk_level() == "Critical"

    def test_multi_screen_adds_risk(self, session):
        session.set_screen_count(3)
        # (3 - 1) × 3 = 6
        assert session.get_risk_score() == 6

    def test_combined_events(self, session):
        session.record_tab_leave()
        session.record_tab_return()     # 2
        session.record_paste_attempt()  # 5
        session.record_fullscreen_exit()  # 4
        expected = 2 + 5 + 4
        assert session.get_risk_score() == expected


# ── Flags ────────────────────────────────────────────────────────────────


class TestFlags:
    def test_no_flags_on_clean_session(self, session):
        assert session.get_flags() == []

    def test_all_flag_types(self, session):
        session.record_tab_leave()
        session.record_tab_return()
        session.record_paste_attempt()
        session.record_fullscreen_exit()
        session.record_multi_face()
        session.record_devtools_attempt()
        session.set_screen_count(2)

        flags = session.get_flags()
        assert len(flags) == 6  # one for each event type
        assert any("Tab" in f for f in flags)
        assert any("paste" in f.lower() for f in flags)
        assert any("fullscreen" in f.lower() for f in flags)
        assert any("face" in f.lower() for f in flags)
        assert any("DevTools" in f for f in flags)
        assert any("monitor" in f.lower() for f in flags)


# ── Summary & Serialization ──────────────────────────────────────────────


class TestSummary:
    def test_summary_keys(self, session):
        session.record_tab_leave()
        session.record_tab_return()
        summary = session.get_summary()

        required_keys = [
            "risk_level", "risk_score", "tab_switch_count",
            "total_time_away", "paste_attempt_count",
            "fullscreen_exit_count", "multi_face_count",
            "devtools_attempt_count", "screen_count",
            "flags", "per_question_tabs", "events",
        ]
        for key in required_keys:
            assert key in summary, f"Missing key: {key}"

    def test_events_are_serializable(self, session):
        import json

        session.record_paste_attempt()
        summary = session.get_summary()
        # Should not raise
        json.dumps(summary)


# ── Reset ────────────────────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_everything(self, session):
        session.record_tab_leave()
        session.record_tab_return()
        session.record_paste_attempt()
        session.record_devtools_attempt()
        session.set_screen_count(3)

        session.reset()

        assert session.tab_switch_count == 0
        assert session.paste_attempt_count == 0
        assert session.fullscreen_exit_count == 0
        assert session.multi_face_count == 0
        assert session.devtools_attempt_count == 0
        assert session.screen_count == 1
        assert session.get_risk_score() == 0
        assert session.get_flags() == []


# ── Thread Safety ────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_event_recording(self, session):
        """Multiple threads recording events should not corrupt state."""
        errors = []

        def record_events():
            try:
                for _ in range(100):
                    session.record_paste_attempt()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_events) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert session.paste_attempt_count == 400
