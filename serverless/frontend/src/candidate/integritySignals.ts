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
  faceNotDetected: number;
  multipleFaces: number;
  events: IntegrityEvent[];
};

/**
 * Collects browser integrity signals (tab switches, copy/paste, devtools)
 * and merges proctoring events (face detection) into a unified signal set.
 */
export function useIntegritySignals(
  questionIndex: number,
  proctoringEvents: ProctoringEvent[] = [],
): IntegritySignals {
  const [events, setEvents] = useState<IntegrityEvent[]>([]);
  const counts = useRef({
    tabSwitches: 0,
    fullscreenExits: 0,
    copyPasteAttempts: 0,
    devtoolsAttempts: 0,
  });

  useEffect(() => {
    function record(type: string) {
      if (type === "tab_switch") counts.current.tabSwitches += 1;
      else if (type === "fullscreen_exit") counts.current.fullscreenExits += 1;
      else if (type === "copyPasteAttempts") counts.current.copyPasteAttempts += 1;
      else if (type === "devtoolsAttempts") counts.current.devtoolsAttempts += 1;

      setEvents((current) => [
        ...current,
        { type, questionIndex, timestamp: new Date().toISOString() },
      ]);
    }

    function onVisibility() {
      if (document.hidden) record("tab_switch");
    }
    function onFullscreen() {
      if (!document.fullscreenElement) record("fullscreen_exit");
    }
    function onCopyPaste() {
      record("copyPasteAttempts");
    }
    function onKeyDown(event: KeyboardEvent) {
      const key = event.key.toLowerCase();
      if (
        event.key === "F12" ||
        (event.ctrlKey && event.shiftKey && ["i", "j"].includes(key)) ||
        (event.ctrlKey && key === "u")
      ) {
        record("devtoolsAttempts");
      }
    }

    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("copy", onCopyPaste);
    document.addEventListener("paste", onCopyPaste);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("fullscreenchange", onFullscreen);
      document.removeEventListener("copy", onCopyPaste);
      document.removeEventListener("paste", onCopyPaste);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [questionIndex]);

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

  return useMemo(
    () => ({
      ...counts.current,
      faceNotDetected,
      multipleFaces,
      events: allEvents,
    }),
    [allEvents, faceNotDetected, multipleFaces],
  );
}
