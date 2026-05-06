import { useEffect, useMemo, useRef, useState } from "react";

export type IntegrityEvent = {
  type: string;
  questionIndex: number;
  timestamp: string;
};

export function useIntegritySignals(questionIndex: number) {
  const [events, setEvents] = useState<IntegrityEvent[]>([]);
  const counts = useRef({
    tabSwitches: 0,
    fullscreenExits: 0,
    copyPasteAttempts: 0,
    devtoolsAttempts: 0,
  });

  useEffect(() => {
    function record(type: keyof typeof counts.current | "fullscreen_exit" | "tab_switch") {
      const normalized = type === "fullscreen_exit" ? "fullscreenExits" : type === "tab_switch" ? "tabSwitches" : type;
      if (normalized in counts.current) {
        counts.current[normalized as keyof typeof counts.current] += 1;
      }
      setEvents((current) => [
        ...current,
        { type: String(type), questionIndex, timestamp: new Date().toISOString() },
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
      if (event.key === "F12" || (event.ctrlKey && event.shiftKey && ["i", "j"].includes(key)) || (event.ctrlKey && key === "u")) {
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

  return useMemo(
    () => ({
      ...counts.current,
      events,
    }),
    [events],
  );
}
