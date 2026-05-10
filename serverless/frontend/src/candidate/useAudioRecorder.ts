import { useRef, useState } from "react";

export type AudioRecording = {
  blob: Blob;
  contentType: string;
  durationSeconds: number;
};

export function useAudioRecorder() {
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<BlobPart[]>([]);
  const startedAt = useRef(0);
  const [isRecording, setIsRecording] = useState(false);
  const [recording, setRecording] = useState<AudioRecording | null>(null);
  const [error, setError] = useState("");

  async function start() {
    setError("");
    setRecording(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Audio recording is not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const contentType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      chunks.current = [];
      recorder.current = new MediaRecorder(stream, { mimeType: contentType });
      startedAt.current = Date.now();
      recorder.current.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.current.push(event.data);
      };
      recorder.current.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks.current, { type: contentType });
        setRecording({
          blob,
          contentType,
          durationSeconds: Math.max(1, Math.round((Date.now() - startedAt.current) / 1000)),
        });
        setIsRecording(false);
      };
      recorder.current.start();
      setIsRecording(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setIsRecording(false);
    }
  }

  function stop() {
    if (recorder.current && recorder.current.state !== "inactive") {
      recorder.current.stop();
    }
  }

  function clear() {
    setRecording(null);
    setError("");
  }

  return { isRecording, recording, error, start, stop, clear };
}
