import { useEffect, useMemo, useRef, useState } from "react";
import type { ProctoringEvent } from "./useProctoring";

export type IntegrityEvent = {
  type: string;
  questionIndex: number;
  timestamp: string;
  detail?: string;
};

export type IntegritySignals = {
  tabSwitches: number;
  fullscreenExits: number;
  copyPasteAttempts: number;
  devtoolsAttempts: number;
  screenCount: number;
  totalTimeAwaySeconds: number;
  faceNotDetected: number;
  multipleFaces: number;
  riskScore: number;
  riskLevel: "Low" | "Medium" | "High" | "Critical";
  flags: string[];
  events: IntegrityEvent[];
};

const ACTIVE_PHASES = new Set(["prep", "recording", "processing", "transcript"]);

/**
 * Collects browser integrity signals (tab switches, copy/paste, devtools)
 * and merges proctoring events (face detection) into a unified signal set.
 */
export function useIntegritySignals(
  questionIndex: number,
  proctoringEvents: ProctoringEvent[] = [],
  phase = "",
): IntegritySignals {
  const [events, setEvents] = useState<IntegrityEvent[]>([]);
  const [, forceRender] = useState(0);
  const counts = useRef({
    tabSwitches: 0,
    fullscreenExits: 0,
    copyPasteAttempts: 0,
    devtoolsAttempts: 0,
    screenCount: 1,
    totalTimeAwaySeconds: 0,
  });
  const leftAt = useRef<number | null>(null);

  useEffect(() => {
    const active = ACTIVE_PHASES.has(phase);

    function record(type: string, detail?: string) {
      if (!active) return;
      if (type === "tab_switch" || type === "window_switch") counts.current.tabSwitches += 1;
      else if (type === "fullscreen_exit") counts.current.fullscreenExits += 1;
      else if (type === "copy_paste_attempt") counts.current.copyPasteAttempts += 1;
      else if (type === "devtools_attempt") counts.current.devtoolsAttempts += 1;

      setEvents((current) => [
        ...current,
        { type, questionIndex, timestamp: new Date().toISOString(), detail },
      ]);
    }

    function recordReturn(type: "tab_switch" | "window_switch") {
      if (!leftAt.current) {
        leftAt.current = null;
        return;
      }
      const awaySeconds = Math.max(0, (Date.now() - leftAt.current) / 1000);
      leftAt.current = null;
      if (awaySeconds < 0.5) return;
      counts.current.totalTimeAwaySeconds += awaySeconds;
      record(type, `Away ${awaySeconds.toFixed(1)}s`);
    }

    function onVisibility() {
      if (!active) return;
      if (document.hidden) {
        leftAt.current = Date.now();
      } else {
        recordReturn("tab_switch");
      }
    }
    function onBlur() {
      if (active && !leftAt.current) leftAt.current = Date.now();
    }
    function onFocus() {
      if (active && !document.hidden) recordReturn("window_switch");
    }
    function onFullscreen() {
      if (!document.fullscreenElement) record("fullscreen_exit");
    }
    function onCopyPaste(event: ClipboardEvent) {
      if (!active) return;
      event.preventDefault();
      record("copy_paste_attempt", event.type);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (!active) return;
      const key = event.key.toLowerCase();
      if (
        event.key === "F12" ||
        (event.ctrlKey && event.shiftKey && ["i", "j", "c"].includes(key)) ||
        (event.ctrlKey && key === "u")
      ) {
        event.preventDefault();
        event.stopPropagation();
        const combo = event.key === "F12" ? "F12" : `${event.ctrlKey ? "Ctrl+" : ""}${event.shiftKey ? "Shift+" : ""}${event.key.toUpperCase()}`;
        record("devtools_attempt", combo);
      }
    }
    function onContextMenu(event: MouseEvent) {
      if (active) event.preventDefault();
    }
    function onMouseLeave() {
      if (active && !leftAt.current) leftAt.current = Date.now();
    }
    function onMouseEnter() {
      if (active && !document.hidden) recordReturn("window_switch");
    }

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("copy", onCopyPaste, true);
    document.addEventListener("paste", onCopyPaste, true);
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("contextmenu", onContextMenu);
    document.addEventListener("mouseleave", onMouseLeave);
    document.addEventListener("mouseenter", onMouseEnter);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("fullscreenchange", onFullscreen);
      document.removeEventListener("copy", onCopyPaste, true);
      document.removeEventListener("paste", onCopyPaste, true);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("contextmenu", onContextMenu);
      document.removeEventListener("mouseleave", onMouseLeave);
      document.removeEventListener("mouseenter", onMouseEnter);
    };
  }, [phase, questionIndex]);

  useEffect(() => {
    if (!ACTIVE_PHASES.has(phase)) return;
    try {
      const screenDetails = screen as Screen & { isExtended?: boolean };
      counts.current.screenCount = screenDetails.isExtended ? 2 : 1;
    } catch {
      counts.current.screenCount = 1;
    }
    forceRender((value) => value + 1);
  }, [phase]);

  // Merge browser integrity events + proctoring face events
  const faceNotDetected = proctoringEvents.filter((e) => e.type === "face_not_detected").length;
  const multipleFaces = proctoringEvents.filter((e) => e.type === "multiple_faces").length;

  const allEvents = useMemo(() => {
    const procAsIntegrity: IntegrityEvent[] = proctoringEvents.map((e) => ({
      type: e.type,
      questionIndex: e.questionIndex,
      timestamp: e.timestamp,
      detail: e.detail,
    }));
    return [...events, ...procAsIntegrity];
  }, [events, proctoringEvents]);

  const baseSignals = counts.current;
  const riskScore = (
    baseSignals.tabSwitches * 2
    + baseSignals.copyPasteAttempts * 5
    + baseSignals.fullscreenExits * 4
    + baseSignals.devtoolsAttempts * 8
    + multipleFaces * 6
    + Math.max(0, baseSignals.screenCount - 1) * 3
  );
  const riskLevel = riskScore >= 40 ? "Critical" : riskScore >= 25 ? "High" : riskScore >= 10 ? "Medium" : "Low";
  const flags = [
    baseSignals.tabSwitches > 0 ? `Tab/window switched ${baseSignals.tabSwitches} time(s)` : "",
    baseSignals.copyPasteAttempts > 0 ? `Copy/paste attempted ${baseSignals.copyPasteAttempts} time(s)` : "",
    baseSignals.fullscreenExits > 0 ? `Fullscreen exited ${baseSignals.fullscreenExits} time(s)` : "",
    baseSignals.devtoolsAttempts > 0 ? `DevTools attempted ${baseSignals.devtoolsAttempts} time(s)` : "",
    multipleFaces > 0 ? `Multiple faces detected ${multipleFaces} time(s)` : "",
    baseSignals.screenCount > 1 ? `Multi-screen detected (${baseSignals.screenCount} screens)` : "",
  ].filter(Boolean);

  return useMemo(
    () => ({
      ...baseSignals,
      totalTimeAwaySeconds: Math.round(baseSignals.totalTimeAwaySeconds * 10) / 10,
      faceNotDetected,
      multipleFaces,
      riskScore,
      riskLevel,
      flags,
      events: allEvents,
    }),
    [allEvents, baseSignals, faceNotDetected, flags, multipleFaces, riskLevel, riskScore],
  );
}
