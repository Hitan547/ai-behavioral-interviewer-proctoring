import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Browser-side proctoring using MediaPipe Face Detection.
 * Runs entirely client-side — no server needed.
 *
 * Tracks: face presence, multiple faces, camera status.
 * Reports: proctoring events for integrity signals.
 */

export type ProctoringEvent = {
  type: "face_not_detected" | "multiple_faces" | "camera_error" | "camera_started" | "camera_stopped";
  questionIndex: number;
  timestamp: string;
  detail?: string;
};

export type ProctoringState = {
  cameraActive: boolean;
  faceDetected: boolean;
  faceCount: number;
  events: ProctoringEvent[];
  faceNotDetectedCount: number;
  multipleFacesCount: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  startCamera: () => Promise<void>;
  stopCamera: () => void;
  error: string;
};

type FaceDetectorInstance = {
  detectForVideo: (video: HTMLVideoElement, timestamp: number) => { detections: unknown[] };
  close: () => void;
};

const MEDIAPIPE_CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18";

// Load MediaPipe via script tag to avoid TypeScript module resolution issues
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.type = "module";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });
}

async function loadFaceDetector(): Promise<FaceDetectorInstance | null> {
  try {
    // Load MediaPipe Vision via dynamic import with Vite ignore
    await loadScript(`${MEDIAPIPE_CDN}/vision_bundle.mjs`);

    // Access the global MediaPipe API — falls back gracefully
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vision = (globalThis as any).vision ?? (globalThis as any).mediapipe;
    if (!vision?.FilesetResolver) {
      // If script-tag approach doesn't expose globals, try dynamic import
      const mod = await (Function('return import("' + MEDIAPIPE_CDN + '/vision_bundle.mjs")')() as Promise<Record<string, unknown>>);
      const resolver = mod.FilesetResolver as { forVisionTasks: (path: string) => Promise<unknown> };
      const fsr = await resolver.forVisionTasks(`${MEDIAPIPE_CDN}/wasm`);
      const FD = mod.FaceDetector as { createFromOptions: (fsr: unknown, opts: unknown) => Promise<FaceDetectorInstance> };
      return await FD.createFromOptions(fsr, {
        baseOptions: {
          modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
          delegate: "GPU",
        },
        runningMode: "VIDEO",
        minDetectionConfidence: 0.5,
      });
    }

    const filesetResolver = await vision.FilesetResolver.forVisionTasks(`${MEDIAPIPE_CDN}/wasm`);
    const detector = await vision.FaceDetector.createFromOptions(filesetResolver, {
      baseOptions: {
        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
        delegate: "GPU",
      },
      runningMode: "VIDEO",
      minDetectionConfidence: 0.5,
    });
    return detector as FaceDetectorInstance;
  } catch {
    console.warn("[proctoring] MediaPipe face detection unavailable — using basic camera monitoring.");
    return null;
  }
}

const DETECTION_INTERVAL_MS = 1500; // Check face every 1.5 seconds

export function useProctoring(questionIndex: number): ProctoringState {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectorRef = useRef<FaceDetectorInstance | null>(null);
  const intervalRef = useRef<number>(0);

  const [cameraActive, setCameraActive] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const [faceCount, setFaceCount] = useState(0);
  const [events, setEvents] = useState<ProctoringEvent[]>([]);
  const [error, setError] = useState("");

  const countsRef = useRef({ faceNotDetected: 0, multipleFaces: 0 });

  const addEvent = useCallback(
    (type: ProctoringEvent["type"], detail?: string) => {
      countsRef.current = {
        ...countsRef.current,
        ...(type === "face_not_detected" ? { faceNotDetected: countsRef.current.faceNotDetected + 1 } : {}),
        ...(type === "multiple_faces" ? { multipleFaces: countsRef.current.multipleFaces + 1 } : {}),
      };
      setEvents((prev) => [
        ...prev,
        { type, questionIndex, timestamp: new Date().toISOString(), detail },
      ]);
    },
    [questionIndex],
  );

  const runDetection = useCallback(() => {
    const video = videoRef.current;
    const detector = detectorRef.current;
    if (!video || !detector || video.readyState < 2) return;

    try {
      const result = detector.detectForVideo(video, performance.now());
      const count = result.detections.length;
      setFaceCount(count);

      if (count === 0) {
        setFaceDetected(false);
        addEvent("face_not_detected");
      } else if (count > 1) {
        setFaceDetected(true);
        addEvent("multiple_faces", `${count} faces detected`);
      } else {
        setFaceDetected(true);
      }

      // Draw to canvas for visual feedback
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          ctx.drawImage(video, 0, 0);

          // Draw face bounding boxes
          ctx.strokeStyle = count === 1 ? "#10b981" : "#ef4444";
          ctx.lineWidth = 3;
          for (const detection of result.detections as Array<{ boundingBox?: { originX: number; originY: number; width: number; height: number } }>) {
            const box = detection.boundingBox;
            if (box) {
              ctx.strokeRect(box.originX, box.originY, box.width, box.height);
            }
          }
        }
      }
    } catch {
      // Detection can fail on some frames — ignore
    }
  }, [addEvent]);

  const startCamera = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraActive(true);
      addEvent("camera_started");

      // Load face detector
      if (!detectorRef.current) {
        detectorRef.current = await loadFaceDetector();
      }

      // Start periodic detection
      intervalRef.current = window.setInterval(runDetection, DETECTION_INTERVAL_MS);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Camera access failed: ${msg}`);
      addEvent("camera_error", msg);
    }
  }, [addEvent, runDetection]);

  const stopCamera = useCallback(() => {
    if (intervalRef.current) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = 0;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
    setFaceDetected(false);
    setFaceCount(0);
    addEvent("camera_stopped");
  }, [addEvent]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      detectorRef.current?.close();
    };
  }, []);

  return {
    cameraActive,
    faceDetected,
    faceCount,
    events,
    faceNotDetectedCount: countsRef.current.faceNotDetected,
    multipleFacesCount: countsRef.current.multipleFaces,
    videoRef,
    canvasRef,
    startCamera,
    stopCamera,
    error,
  };
}
