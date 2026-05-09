import {
  Camera, CheckCircle2, ChevronRight, Clock, LogOut, Maximize2, Mic, MicOff,
  Play, RotateCcw, Shield, Video
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiClient } from "../api/client";
import type { AuthSession } from "../auth/useAuthSession";
import { AudioRecorder } from "./AudioRecorder";
import { useIntegritySignals } from "./integritySignals";
import { SpeechSynth } from "./SpeechSynth";
import { useFaceProctoring } from "./useProctoring";

type Props = { auth: AuthSession };

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
};

type Phase =
  | "start"        // consent
  | "camera_setup" // camera + mic check
  | "prep"         // show question + 15s timer
  | "recording"    // 60s audio capture
  | "processing"   // transcribing
  | "transcript"   // review answer
  | "report";      // done

type InterviewQuestion = { questionIndex: number; question: string; keywords: string[] };
type DemoAnswer = { text: string; audioBlob: Blob | null; duration: number };
type DemoScore = {
  finalScore: number;
  baseScore: number;
  integrityPenalty: number;
  recommendation: string;
  perQuestion: Array<{
    questionIndex: number;
    question: string;
    score: number;
    verdict: string;
    summary: string;
    dimensions: {
      clarity: number;
      relevance: number;
      starQuality: number;
      specificity: number;
      communication: number;
      jobFit: number;
    };
  }>;
};

const PREP_TIME = 15;
const RECORD_TIME = 60;
const STEPS = ["Setup", "Camera Check", "Interview", "Complete"];
const SWITCH_EVENT_TYPES = new Set(["tab_switch", "window_switch", "copy_paste_attempt", "devtools_attempt"]);

// ── Demo questions for demo mode ──
const DEMO_QUESTIONS: InterviewQuestion[] = [
  { questionIndex: 0, question: "Tell me about a time you had to learn a new technology quickly to meet a project deadline. What was your approach?", keywords: ["learning", "deadline", "approach"] },
  { questionIndex: 1, question: "Describe a situation where you disagreed with a team member on a technical decision. How did you handle it?", keywords: ["teamwork", "conflict", "resolution"] },
  { questionIndex: 2, question: "Give an example of a challenging bug you debugged. What steps did you take to identify and fix it?", keywords: ["debugging", "problem-solving", "systematic"] },
  { questionIndex: 3, question: "Tell me about a project where you had to balance multiple competing priorities. How did you manage your time?", keywords: ["prioritization", "time-management"] },
  { questionIndex: 4, question: "Describe a time when you received critical feedback on your work. How did you respond and what did you learn?", keywords: ["feedback", "growth", "self-improvement"] },
];

function clampScore(value: number) {
  return Math.max(0, Math.min(10, Math.round(value)));
}

function countMatches(text: string, terms: string[]) {
  const lower = text.toLowerCase();
  return terms.filter((term) => term.length > 2 && lower.includes(term.toLowerCase())).length;
}

function scoreDemoAnswer(question: InterviewQuestion, answer: DemoAnswer | undefined) {
  const text = (answer?.text || "").trim();
  const words = text ? text.split(/\s+/).filter(Boolean) : [];
  const wordCount = words.length;
  if (!wordCount) {
    return {
      questionIndex: question.questionIndex,
      question: question.question,
      score: 0,
      verdict: "Missing",
      summary: "No answer was captured for this question.",
      dimensions: { clarity: 0, relevance: 0, starQuality: 0, specificity: 0, communication: 0, jobFit: 0 },
    };
  }

  const questionTerms = question.question
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 5);
  const relevanceHits = countMatches(text, [...question.keywords, ...questionTerms.slice(0, 8)]);
  const starHits = countMatches(text, ["situation", "task", "action", "result", "impact", "learned", "outcome", "because"]);
  const specificHits = countMatches(text, ["project", "team", "customer", "deadline", "metric", "production", "users", "weeks", "days"]);
  const hasNumbers = /\d|%/.test(text);
  const sentenceCount = Math.max(1, text.split(/[.!?]+/).filter((part) => part.trim()).length);

  const dimensions = {
    clarity: clampScore(Math.min(wordCount / 10, 6) + Math.min(sentenceCount, 4)),
    relevance: clampScore(3 + relevanceHits * 1.5),
    starQuality: clampScore(2 + starHits * 1.4),
    specificity: clampScore(2 + specificHits * 1.2 + (hasNumbers ? 2 : 0) + Math.min(wordCount / 30, 2)),
    communication: clampScore(3 + Math.min(wordCount / 18, 4) + Math.min(sentenceCount, 3)),
    jobFit: clampScore(3 + countMatches(text, question.keywords) * 2 + Math.min(relevanceHits, 3)),
  };
  const weighted = (
    dimensions.clarity * 0.15
    + dimensions.relevance * 0.20
    + dimensions.starQuality * 0.15
    + dimensions.specificity * 0.20
    + dimensions.communication * 0.15
    + dimensions.jobFit * 0.15
  );
  const score = Math.round(weighted * 10);
  const verdict = score >= 75 ? "Strong" : score >= 55 ? "Needs Review" : "Weak";
  return {
    questionIndex: question.questionIndex,
    question: question.question,
    score,
    verdict,
    summary: `Length: ${wordCount} words. Relevance hits: ${relevanceHits}. STAR/impact markers: ${starHits}. Specific detail markers: ${specificHits}${hasNumbers ? " plus numbers/metrics" : ""}.`,
    dimensions,
  };
}

function buildDemoScore(
  questions: InterviewQuestion[],
  answers: DemoAnswer[],
  riskLevel: string,
): DemoScore {
  const perQuestion = questions.map((question, index) => scoreDemoAnswer(question, answers[index]));
  const answered = perQuestion.filter((item) => item.score > 0);
  const baseScore = answered.length
    ? Math.round(answered.reduce((total, item) => total + item.score, 0) / answered.length)
    : 0;
  const integrityPenalty = riskLevel === "Critical" ? 15 : riskLevel === "High" ? 10 : riskLevel === "Medium" ? 5 : 0;
  const finalScore = Math.max(0, Math.min(100, baseScore - integrityPenalty));
  const recommendation = ["High", "Critical"].includes(riskLevel) && baseScore >= 60
    ? "Manual Review Required"
    : finalScore >= 75
    ? "Strong Fit"
    : finalScore < 50
      ? "Not Recommended"
      : "Needs Review";
  return { finalScore, baseScore, integrityPenalty, recommendation, perQuestion };
}

export function CandidateInterview({ auth }: Props) {
  const api = useMemo(() => new ApiClient(auth), [auth]);
  const isDemo = auth.isDemoMode;

  // URL params
  const params = new URLSearchParams(window.location.search);
  const jobId = params.get("jobId") || auth.candidateJobId || "";
  const candidateId = params.get("candidateId") || auth.candidateId || "";
  const isPracticeMode = isDemo || (auth.role !== "candidate" && !jobId && !candidateId);

  // Interview state
  const [phase, setPhase] = useState<Phase>("start");
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [qIndex, setQIndex] = useState(0);
  const [candidateName, setCandidateName] = useState(auth.role === "candidate" ? auth.username : "Demo Candidate");
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [status, setStatus] = useState("");

  // Camera + mic
  const videoRef = useRef<HTMLVideoElement>(null);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [micReady, setMicReady] = useState(false);

  // Audio recording
  const recorderRef = useRef(new AudioRecorder());
  const synthRef = useRef(new SpeechSynth());
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const speechTranscriptRef = useRef("");
  const recognitionActiveRef = useRef(false);

  // Timer
  const [timeLeft, setTimeLeft] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const phaseRef = useRef<Phase>("start");
  const stopInProgressRef = useRef(false);

  // Answers
  const [answers, setAnswers] = useState<DemoAnswer[]>([]);
  const [currentTranscript, setCurrentTranscript] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");
  const [speechRecognitionAvailable, setSpeechRecognitionAvailable] = useState(true);
  const [retryUsed, setRetryUsed] = useState(false);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [submissionStatus, setSubmissionStatus] = useState("");

  // Proctoring: browser-only signals, compatible with the AWS serverless path.
  const isIntegrityActive = phase === "prep" || phase === "recording" || phase === "processing" || phase === "transcript";
  const faceProctoring = useFaceProctoring(videoRef, Boolean(cameraStream) && isIntegrityActive, qIndex);
  const proctoring = useIntegritySignals(qIndex, faceProctoring.events, phase);
  const [fullscreenPrompt, setFullscreenPrompt] = useState(false);
  const [integrityNotice, setIntegrityNotice] = useState<{ title: string; message: string; severity: "yellow" | "orange" | "red" } | null>(null);
  const seenIntegrityEvents = useRef(0);
  const demoScore = useMemo(
    () => isPracticeMode ? buildDemoScore(questions, answers, proctoring.riskLevel) : null,
    [answers, isPracticeMode, proctoring.riskLevel, questions],
  );

  useEffect(() => {
    phaseRef.current = phase;
    if (phase !== "processing") {
      stopInProgressRef.current = false;
    }
  }, [phase]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      recorderRef.current.destroy();
      recognitionActiveRef.current = false;
      recognitionRef.current?.stop();
      synthRef.current.cancel();
      if (timerRef.current) clearInterval(timerRef.current);
      if (cameraStream) cameraStream.getTracks().forEach((t) => t.stop());
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !cameraStream) return;
    video.srcObject = cameraStream;
    video.play().catch(() => {
      setStatus("Camera is active, but preview playback was blocked. Click the video area or refresh and try again.");
    });
  }, [cameraStream, phase]);

  useEffect(() => {
    if (!isIntegrityActive) {
      setFullscreenPrompt(false);
      setIntegrityNotice(null);
      return;
    }
    const onFullscreenChange = () => {
      setFullscreenPrompt(!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    onFullscreenChange();
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [isIntegrityActive]);

  useEffect(() => {
    if (!isIntegrityActive) {
      seenIntegrityEvents.current = proctoring.events.length;
      return;
    }
    const newEvents = proctoring.events.slice(seenIntegrityEvents.current);
    seenIntegrityEvents.current = proctoring.events.length;
    const latest = [...newEvents].reverse().find((event) => SWITCH_EVENT_TYPES.has(event.type));
    if (!latest) return;
    const severity = proctoring.riskScore >= 25 ? "red" : proctoring.riskScore >= 10 ? "orange" : "yellow";
    const title = latest.type === "tab_switch" || latest.type === "window_switch"
      ? "Switch Detected"
      : latest.type === "copy_paste_attempt"
        ? "Copy/Paste Blocked"
        : "Restricted Shortcut Blocked";
    const message = latest.type === "tab_switch" || latest.type === "window_switch"
      ? "Leaving the interview window is recorded as an integrity signal for recruiter review."
      : latest.type === "copy_paste_attempt"
        ? "Copy and paste are disabled during the interview."
        : "Developer tools shortcuts are disabled during the interview.";
    setIntegrityNotice({ title, message, severity });
  }, [isIntegrityActive, proctoring.events, proctoring.riskScore]);

  // Stepper
  function stepIndex(): number {
    if (phase === "start") return 0;
    if (phase === "camera_setup") return 1;
    if (phase === "report") return 3;
    return 2;
  }

  // ── START PHASE ──
  async function handleStartInterview() {
    if (!consentAccepted) { setStatus("Please accept the AI interview notice."); return; }
    if (!candidateName.trim()) { setStatus("Please enter your name."); return; }
    if (!isPracticeMode && (!jobId || !candidateId)) {
      setStatus("Candidate login did not include an interview assignment. Please use the credentials from your invite email.");
      return;
    }

    setStatus("Loading interview questions...");
    try {
      if (isPracticeMode) {
        setQuestions(DEMO_QUESTIONS);
      } else {
        const data = await api.getCandidateInterview(jobId, candidateId);
        setQuestions(data.interview.questions);
        setCandidateName(data.interview.candidateName || candidateName);
      }
      setPhase("camera_setup");
      setStatus("");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Failed to load interview");
    }
  }

  // ── CAMERA SETUP ──
  async function setupCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 15 } },
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      setCameraStream(stream);
      setCameraReady(true);
      const micOk = recorderRef.current.useStream(stream) || await recorderRef.current.requestMicAccess();
      setMicReady(micOk);
    } catch {
      setStatus("Camera/microphone access denied. Please allow permissions.");
    }
  }

  async function startInterview() {
    if (phaseRef.current !== "camera_setup") return;
    try {
      await document.documentElement.requestFullscreen?.();
      setFullscreenPrompt(false);
    } catch {
      setFullscreenPrompt(true);
    }
    clearTimer();
    setPhase("prep");
    startPrepTimer();
  }

  async function reEnterFullscreen() {
    try {
      await document.documentElement.requestFullscreen?.();
      setFullscreenPrompt(false);
    } catch {
      setFullscreenPrompt(true);
    }
  }

  async function handleSignOut() {
    clearTimer();
    synthRef.current.cancel();
    recognitionActiveRef.current = false;
    recognitionRef.current?.stop();
    if (recorderRef.current.state === "recording") {
      await recorderRef.current.stop();
    }
    cameraStream?.getTracks().forEach((track) => track.stop());
    if (document.fullscreenElement) {
      await document.exitFullscreen().catch(() => {});
    }
    auth.clearSession();
  }

  function clearTimer() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  // ── PREP PHASE ──
  const startPrepTimer = useCallback((questionIndex = qIndex) => {
    clearTimer();
    setTimeLeft(PREP_TIME);
    setRetryUsed(false);
    setLiveTranscript("");
    speechTranscriptRef.current = "";
    // Read question aloud
    const q = questions[questionIndex];
    if (q) synthRef.current.speak(q.question).catch(() => {});

    let remaining = PREP_TIME;
    timerRef.current = setInterval(() => {
      remaining -= 1;
      setTimeLeft(Math.max(remaining, 0));
      if (remaining <= 0) {
        clearTimer();
        if (phaseRef.current === "prep") {
          startRecording();
        }
      }
    }, 1000);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qIndex, questions]);

  // ── RECORDING PHASE ──
  function startRecording() {
    if (phaseRef.current === "recording" || recorderRef.current.state === "recording") {
      return;
    }
    clearTimer();
    synthRef.current.cancel();
    const recordingStarted = recorderRef.current.start();
    if (!recordingStarted) {
      setCurrentTranscript("");
      setStatus(recorderRef.current.error || "Could not start microphone recording.");
      setPhase("transcript");
      return;
    }
    if (isPracticeMode) {
      startPracticeSpeechRecognition();
    }
    phaseRef.current = "recording";
    setPhase("recording");
    setTimeLeft(RECORD_TIME);

    let remaining = RECORD_TIME;
    timerRef.current = setInterval(() => {
      remaining -= 1;
      setTimeLeft(Math.max(remaining, 0));
      if (remaining <= 0) {
        clearTimer();
        void stopRecording();
      }
    }, 1000);
  }

  async function stopRecording() {
    if (stopInProgressRef.current || phaseRef.current !== "recording") {
      return;
    }
    stopInProgressRef.current = true;
    clearTimer();
    phaseRef.current = "processing";
    setPhase("processing");

    if (isPracticeMode) {
      recognitionActiveRef.current = false;
      recognitionRef.current?.stop();
      const blob = await stopRecorderWithTimeout();
      await new Promise((r) => setTimeout(r, 500));
      let transcript = (speechTranscriptRef.current || liveTranscript).trim();
      if (!blob || blob.size < 1200) {
        setCurrentTranscript(transcript);
        setStatus("Microphone recording was empty. Check the browser microphone input and try re-recording.");
        setPhase("transcript");
        return;
      }
      if (!transcript && blob && auth.apiBaseUrl && auth.accessToken) {
        try {
          setStatus("Browser live transcript was unavailable. Transcribing recorded audio with serverless Whisper...");
          const contentType = normalizeAudioContentType(blob.type);
          const result = await api.transcribePracticeAudio({
            audioBase64: await blobToBase64(blob),
            filename: `practice-q-${qIndex}.${recorderRef.current.getFileExtension()}`,
            contentType,
            questionIndex: qIndex,
            prompt: questions[qIndex]?.question || "",
          });
          transcript = result.transcription.transcript.trim();
        } catch (err) {
          setStatus(err instanceof Error ? err.message : "Serverless transcription failed. You can type your answer below.");
        }
      }
      setCurrentTranscript(transcript);
      if (!transcript) {
        setStatus(
          `Recorded audio reached Whisper, but no speech was detected (${Math.round(blob.size / 1024)} KB). Check microphone input, speak louder, or type your answer below.`,
        );
      } else {
        setStatus("");
      }
      setPhase("transcript");
      return;
    }

    const blob = await recorderRef.current.stop();
    console.log("[CandidateInterview] stopRecording result:", blob ? `${blob.size} bytes` : "null");

    if (!blob) {
      setCurrentTranscript("");
      const recError = recorderRef.current.error;
      setStatus(recError || "No audio captured. Check microphone permissions and try Re-record.");
      setPhase("transcript");
      return;
    }

    if (blob.size < 1200) {
      setCurrentTranscript("");
      setStatus(`Audio file too small (${blob.size} bytes). Speak louder or check mic input.`);
      setPhase("transcript");
      return;
    }

    try {
      // Upload audio to S3
      const contentType = normalizeAudioContentType(blob.type);
      const upload = await api.createAudioUpload(jobId, candidateId, {
        questionIndex: qIndex,
        contentType,
      });
      await api.uploadAudio(upload.audioUpload, blob);

      // Request transcription
      const result = await api.transcribeQuestionAudio(jobId, candidateId, qIndex, {
        audioS3Bucket: upload.audioUpload.bucket,
        audioS3Key: upload.audioUpload.key,
        contentType,
      });
      setCurrentTranscript(result.transcription.transcript);
    } catch (err) {
      setCurrentTranscript("");
      setStatus(err instanceof Error ? err.message : "Transcription failed");
    }
    setPhase("transcript");
  }

  // ── TRANSCRIPT / SUBMIT ──
  function handleReRecord() {
    setRetryUsed(true);
    setCurrentTranscript("");
    setLiveTranscript("");
    speechTranscriptRef.current = "";
    recognitionActiveRef.current = false;
    setStatus("");
    setPhase("prep");
    startPrepTimer(qIndex);
  }

  function startPracticeSpeechRecognition(resetTranscript = true) {
    const SpeechRecognitionImpl = (
      window as typeof window & {
        SpeechRecognition?: SpeechRecognitionConstructor;
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
      }
    ).SpeechRecognition || (
      window as typeof window & {
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
      }
    ).webkitSpeechRecognition;

    recognitionActiveRef.current = true;
    if (resetTranscript) {
      speechTranscriptRef.current = "";
      setLiveTranscript("");
    }

    if (!SpeechRecognitionImpl) {
      setSpeechRecognitionAvailable(false);
      return;
    }

    setSpeechRecognitionAvailable(true);
    const recognition = new SpeechRecognitionImpl();
    let sessionFinalText = "";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-IN";
    recognition.onresult = (event) => {
      const finalParts: string[] = [];
      let interimText = "";
      for (let i = 0; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript || "";
        if (result.isFinal) {
          finalParts.push(text.trim());
        } else {
          interimText = `${interimText} ${text}`.trim();
        }
      }
      sessionFinalText = finalParts.join(" ").trim();
      setLiveTranscript(`${speechTranscriptRef.current} ${sessionFinalText} ${interimText}`.trim());
    };
    recognition.onerror = (event) => {
      if (event.error === "no-speech" || event.error === "aborted") {
        return;
      }
      setSpeechRecognitionAvailable(false);
    };
    recognition.onend = () => {
      if (sessionFinalText) {
        speechTranscriptRef.current = `${speechTranscriptRef.current} ${sessionFinalText}`.trim();
        sessionFinalText = "";
        setLiveTranscript(speechTranscriptRef.current);
      }
      if (recognitionActiveRef.current) {
        window.setTimeout(() => startPracticeSpeechRecognition(false), 120);
      }
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setSpeechRecognitionAvailable(false);
    }
  }

  async function stopRecorderWithTimeout(): Promise<Blob | null> {
    return await Promise.race([
      recorderRef.current.stop(),
      new Promise<null>((resolve) => window.setTimeout(() => resolve(null), 8000)),
    ]);
  }

  function normalizeAudioContentType(value: string): string {
    return (value || "audio/webm").split(";", 1)[0].trim().toLowerCase() || "audio/webm";
  }

  function blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const value = String(reader.result || "");
        resolve(value.includes(",") ? value.split(",", 2)[1] : value);
      };
      reader.onerror = () => reject(new Error("Could not read recorded audio."));
      reader.readAsDataURL(blob);
    });
  }

  async function submitAnswer() {
    if (submitBusy) return;
    if (!currentTranscript.trim()) {
      setStatus("Please record an answer before submitting this question.");
      return;
    }
    const newAnswers = [...answers, {
      text: currentTranscript,
      audioBlob: null,
      duration: RECORD_TIME,
    }];

    if (qIndex + 1 >= questions.length) {
      // Submit all answers
      if (!isPracticeMode) {
        setSubmitBusy(true);
        setStatus("");
        setSubmissionStatus("Saving interview and starting AI report generation...");
        try {
          const result = await api.submitCandidateInterview(jobId, candidateId, {
            consentAccepted: true,
            answers: newAnswers.map((a, i) => ({
              questionIndex: i,
              answerText: a.text,
              durationSeconds: a.duration,
            })),
            integritySignals: proctoring,
          });
          setSubmissionStatus(
            result.scoring?.started
              ? "Saved. AI scoring and report generation have started for the recruiter."
              : `Saved. ${result.scoring?.reason || "The recruiter can start scoring from the dashboard."}`,
          );
        } catch (err) {
          setSubmitBusy(false);
          setSubmissionStatus("");
          setStatus(err instanceof Error ? err.message : "Interview submission failed. Please try again.");
          return;
        }
      }
      setAnswers(newAnswers);
      setPhase("report");
      setSubmitBusy(false);
    } else {
      setAnswers(newAnswers);
      const nextIndex = qIndex + 1;
      setQIndex(nextIndex);
      setCurrentTranscript("");
      setPhase("prep");
      setTimeout(() => startPrepTimer(nextIndex), 200);
    }
  }

  // ── RENDER ──
  const currentQ = questions[qIndex];

  return (
    <div className="candidate-panel">
      {/* Stepper */}
      <div className="interview-stepper">
        {STEPS.map((label, i) => (
          <span key={label} className={i === stepIndex() ? "active" : i < stepIndex() ? "done" : ""}>
            {i < stepIndex() ? "✓" : i + 1} {label}
          </span>
        ))}
      </div>

      {/* Proctoring bar (visible during active interview) */}
      {(phase === "prep" || phase === "recording" || phase === "processing" || phase === "transcript") && (
        <div className="proctoring-bar">
          <div className="proctoring-status">
            <div className={`proctoring-indicator ${proctoring.tabSwitches === 0 ? "ok" : "warning"}`}>
              <Shield size={14} /> {proctoring.riskScore === 0 ? "Proctored" : `Risk: ${proctoring.riskLevel}`}
            </div>
            <span className="proctoring-events">
              Tab {proctoring.tabSwitches} · Fullscreen {proctoring.fullscreenExits} · Copy/Paste {proctoring.copyPasteAttempts} · DevTools {proctoring.devtoolsAttempts} · Faces {proctoring.multipleFaces}
            </span>
          </div>
          <button className="proctoring-exit" onClick={handleSignOut} title="Sign out and exit fullscreen">
            <LogOut size={14} /> Sign out
          </button>
          {cameraStream && (
            <div className="camera-preview">
              <video ref={videoRef} autoPlay muted playsInline style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </div>
          )}
        </div>
      )}

      {integrityNotice && !fullscreenPrompt && (
        <div className={`integrity-overlay ${integrityNotice.severity}`}>
          <div className="integrity-modal">
            <Shield size={28} />
            <h3>{integrityNotice.title}</h3>
            <p>{integrityNotice.message}</p>
            <button onClick={() => setIntegrityNotice(null)}>I Understand</button>
          </div>
        </div>
      )}

      {fullscreenPrompt && isIntegrityActive && (
        <div className="integrity-overlay fullscreen">
          <div className="integrity-modal">
            <Maximize2 size={30} />
            <h3>Fullscreen Mode Required</h3>
            <p>Fullscreen was exited. Press Esc is allowed, but the interview must return to fullscreen to continue.</p>
            <div className="integrity-actions">
              <button onClick={reEnterFullscreen}>
                <Maximize2 size={16} /> Re-enter Fullscreen
              </button>
              <button className="secondary-btn" onClick={handleSignOut}>
                <LogOut size={16} /> Sign out
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ════════ START ════════ */}
      {phase === "start" && (
        <div className="gate-card">
          <h3>Welcome, {candidateName || "Candidate"} 👋</h3>
          <p>
            {isPracticeMode
              ? "Practice the candidate interview flow locally with sample behavioral questions."
              : "Your recruiter has prepared this interview from your resume and the job description."}
          </p>

          <div className="consent-notice">
            <strong>AI-assisted interview notice</strong>
            <p>
              This interview uses AI-assisted tools to generate questions, transcribe answers,
              score structured responses, and collect integrity signals such as tab changes,
              fullscreen exits, copy/paste attempts, developer tool attempts, and camera face
              visibility. Recruiters review these outputs as decision-support signals, not final
              hiring decisions.
            </p>
          </div>

          <label className="consent">
            <input type="checkbox" checked={consentAccepted} onChange={(e) => setConsentAccepted(e.target.checked)} />
            <span>
              I understand and agree to the AI-assisted interview, transcription, scoring, and integrity signal collection.
              {" "}
              <a href="?page=proctoring" target="_blank" rel="noreferrer">Review proctoring notice</a>
            </span>
          </label>

          <div className="start-form">
            <label>
              <span>Your Name</span>
              <input value={candidateName} onChange={(e) => setCandidateName(e.target.value)} placeholder="Enter your full name" />
            </label>
          </div>

          <div className="interview-meta">
            <div className="meta-card"><span className="meta-value">5</span><span className="meta-label">Questions</span></div>
            <div className="meta-card"><span className="meta-value">60s</span><span className="meta-label">Per answer</span></div>
            <div className="meta-card"><span className="meta-value">~10m</span><span className="meta-label">Total time</span></div>
          </div>

          {status && <div className="login-status error">{status}</div>}

          <button onClick={handleStartInterview}>
            <Play size={17} /> Begin Setup →
          </button>
        </div>
      )}

      {/* ════════ CAMERA SETUP ════════ */}
      {phase === "camera_setup" && (
        <div className="gate-card">
          <h3>Camera & Microphone Check</h3>
          <p>Allow camera access — make sure you're well lit and centred.</p>

          {!cameraReady ? (
            <>
              <button onClick={setupCamera}>
                <Camera size={17} /> Enable Camera & Microphone
              </button>
              <p className="hint-text">Click the button above, then allow permissions when prompted.</p>
            </>
          ) : (
            <>
              <div className="device-check">
                <div className="device-card">
                  <Video size={20} />
                  <strong>Camera</strong>
                  <div className="device-status">{cameraReady ? "✅ Camera active" : "❌ Camera not found"}</div>
                </div>
                <div className="device-card">
                  {micReady ? <Mic size={20} /> : <MicOff size={20} />}
                  <strong>Microphone</strong>
                  <div className="device-status">{micReady ? "✅ Mic ready" : "❌ Mic not ready"}</div>
                </div>
              </div>

              <div className="camera-preview-large">
                <video ref={videoRef} autoPlay muted playsInline />
              </div>

              {cameraReady && micReady && (
                <div className="ready-banner">
                  <CheckCircle2 size={18} /> Everything looks good!
                </div>
              )}

              <button onClick={startInterview} disabled={!cameraReady || !micReady}>
                <Play size={17} /> Start Interview →
              </button>
            </>
          )}

          {status && <div className="login-status error">{status}</div>}
        </div>
      )}

      {/* ════════ PREP ════════ */}
      {phase === "prep" && currentQ && (
        <div>
          <div className="q-progress">
            <span className="q-label">Question {qIndex + 1} of {questions.length}</span>
            <progress value={qIndex} max={questions.length} />
          </div>

          <div className="question-card prep">
            <span className="q-badge">Read the question</span>
            <p className="q-text">{currentQ.question}</p>
          </div>

          <div className="timer-display">
            <div className="timer-box">
              <span className="timer-value">{timeLeft}</span>
              <span className="timer-unit">sec</span>
            </div>
            <div className="timer-info">
              <strong>Prepare your answer</strong>
              <span>Recording starts automatically when the timer reaches zero.</span>
            </div>
          </div>
          <progress className="full-progress" value={PREP_TIME - timeLeft} max={PREP_TIME} />
        </div>
      )}

      {/* ════════ RECORDING ════════ */}
      {phase === "recording" && currentQ && (
        <div>
          <div className="q-progress">
            <span className="q-label">Question {qIndex + 1} of {questions.length}</span>
            <progress value={qIndex} max={questions.length} />
          </div>

          <div className="question-card recording">
            <div className="rec-indicator">
              <span className="rec-dot" /> Recording in progress
            </div>
            <p className="q-text">{currentQ.question}</p>
          </div>

          <div className="timer-display recording">
            <div className="timer-box danger">
              <span className="timer-value">{timeLeft}</span>
              <span className="timer-unit">sec remaining</span>
            </div>
            <div className="timer-info">
              <strong>Speak your answer clearly</strong>
              <span>
                {isPracticeMode
                  ? speechRecognitionAvailable
                    ? "Live transcript may appear here; if it does not, serverless Whisper will transcribe after recording."
                    : "Your browser cannot live-transcribe here; serverless Whisper will transcribe after recording."
                  : "Use the STAR method — Situation · Task · Action · Result"}
              </span>
            </div>
          </div>
          <progress className="full-progress recording" value={RECORD_TIME - timeLeft} max={RECORD_TIME} />

          {isPracticeMode && (
            <div className={`transcript-card ${liveTranscript ? "has-text" : "empty"}`} style={{ marginTop: 16 }}>
              <span className="transcript-label">{liveTranscript ? "Live transcript" : "Listening for speech"}</span>
              <p>{liveTranscript || "Start speaking. If no words appear, finish recording; the backend will try Whisper transcription."}</p>
            </div>
          )}

          <button style={{ marginTop: 16 }} onClick={stopRecording}>
            Submit Early →
          </button>
        </div>
      )}

      {/* ════════ PROCESSING ════════ */}
      {phase === "processing" && (
        <div className="processing-card">
          <div className="processing-spinner" />
          <h3>Transcribing your answer…</h3>
          <p>Using Whisper AI — this takes a few seconds.</p>
        </div>
      )}

      {/* ════════ TRANSCRIPT ════════ */}
      {phase === "transcript" && currentQ && (
        <div>
          <div className="q-progress">
            <span className="q-label">Question {qIndex + 1} of {questions.length} — Review</span>
            <progress value={(qIndex + 1)} max={questions.length} />
          </div>

          <div className="question-card">
            <span className="q-badge">Question</span>
            <p className="q-text">{currentQ.question}</p>
          </div>

          <div className={`transcript-card ${currentTranscript ? "has-text" : "empty"}`}>
            <span className="transcript-label">{currentTranscript ? "Your transcript" : "No speech detected"}</span>
            <p>{currentTranscript || "No speech was detected. Please use the Re-record button below."}</p>
          </div>

          {isPracticeMode && (
            <label className="manual-transcript">
              <span>Edit or type your answer</span>
              <textarea
                value={currentTranscript}
                placeholder="Type your answer here if browser speech recognition did not capture it."
                onChange={(e) => {
                  setCurrentTranscript(e.target.value);
                  if (e.target.value.trim()) setStatus("");
                }}
              />
            </label>
          )}

          {status && <div className="login-status error">{status}</div>}
          {submissionStatus && <div className="login-status success">{submissionStatus}</div>}

          <div className="transcript-actions">
            {!retryUsed ? (
              <button className="secondary-btn" onClick={handleReRecord}>
                <RotateCcw size={16} /> Re-record
              </button>
            ) : (
              <span className="hint-text">Re-record already used</span>
            )}
            <button onClick={submitAnswer} disabled={submitBusy}>
              {submitBusy
                ? "Saving..."
                : qIndex + 1 >= questions.length
                  ? "Submit & Finish Interview"
                  : `Submit & Next Question (${qIndex + 1}/${questions.length})`}
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ════════ REPORT ════════ */}
      {phase === "report" && (
        <div className="completion-card">
          <div className="completion-icon">✅</div>
          <h3>Interview Complete!</h3>
          <p>
            Thank you, <strong>{candidateName}</strong>.{" "}
            {isPracticeMode
              ? "Your demo responses were captured in this browser session."
              : "Your responses have been saved and submitted for recruiter review."}
          </p>

          <div className="completion-status">
            {isPracticeMode ? "Demo result preview" : submissionStatus || "Saved for recruiter review"}
          </div>

          <div className="interview-meta">
            <div className="meta-card"><span className="meta-value">{answers.length}</span><span className="meta-label">Questions answered</span></div>
            <div className="meta-card"><span className="meta-value">{isPracticeMode ? "Demo" : "Submitted"}</span><span className="meta-label">Interview status</span></div>
            <div className="meta-card"><span className="meta-value">{isPracticeMode ? "Local only" : "Queued"}</span><span className="meta-label">Results</span></div>
          </div>

          {isPracticeMode ? (
            <div className="demo-result-card">
              {demoScore && (
                <div className="demo-score-card">
                  <strong>Demo behavioral score</strong>
                  <div className="result">
                    <div><span className="metric">{demoScore.finalScore}</span><p>Final score</p></div>
                    <div><span className="metric text">{demoScore.recommendation}</span><p>Recommendation</p></div>
                    <div><span className="metric text">-{demoScore.integrityPenalty}</span><p>Integrity penalty</p></div>
                  </div>
                  <p className="demo-score-formula">
                    Base score {demoScore.baseScore}/100 minus integrity penalty. Per question: 15% clarity, 20% relevance, 15% STAR quality, 20% specificity, 15% communication, 15% job fit.
                  </p>
                  <div className="demo-score-list">
                    {demoScore.perQuestion.map((item) => (
                      <div className="demo-score-item" key={item.questionIndex}>
                        <div className="demo-score-head">
                          <span className="q-badge">Question {item.questionIndex + 1}</span>
                          <strong>{item.score}/100</strong>
                          <span className={`verdict-pill ${item.verdict === "Strong" ? "strong" : item.verdict === "Needs Review" ? "review" : item.verdict === "Weak" ? "weak" : "missing"}`}>
                            {item.verdict}
                          </span>
                        </div>
                        <p>{item.summary}</p>
                        <div className="score-dimensions">
                          <div className="dimension-card"><span className="dim-score">{item.dimensions.clarity}</span><span className="dim-label">Clarity</span></div>
                          <div className="dimension-card"><span className="dim-score">{item.dimensions.relevance}</span><span className="dim-label">Relevance</span></div>
                          <div className="dimension-card"><span className="dim-score">{item.dimensions.starQuality}</span><span className="dim-label">STAR</span></div>
                          <div className="dimension-card"><span className="dim-score">{item.dimensions.specificity}</span><span className="dim-label">Specificity</span></div>
                          <div className="dimension-card"><span className="dim-score">{item.dimensions.communication}</span><span className="dim-label">Communication</span></div>
                          <div className="dimension-card"><span className="dim-score">{item.dimensions.jobFit}</span><span className="dim-label">Job fit</span></div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <strong>Captured answers</strong>
              <div className="demo-answer-list">
                {questions.map((question, index) => {
                  const answer = answers[index];
                  return (
                    <div className="demo-answer-item" key={question.questionIndex}>
                      <span className="q-badge">Question {index + 1}</span>
                      <p className="q-text">{question.question}</p>
                      <div className={`transcript-card ${answer?.text ? "has-text" : "empty"}`}>
                        <span className="transcript-label">
                          {answer?.text ? "Captured transcript" : "No transcript captured"}
                        </span>
                        <p>{answer?.text || "No speech was detected for this answer."}</p>
                      </div>
                      <span className="hint-text">Duration: {answer?.duration ?? 0}s</span>
                    </div>
                  );
                })}
              </div>
              <div className="demo-integrity-grid">
                <div><strong>{proctoring.tabSwitches}</strong><span>Tab switches</span></div>
                <div><strong>{proctoring.fullscreenExits}</strong><span>Fullscreen exits</span></div>
                <div><strong>{proctoring.copyPasteAttempts}</strong><span>Copy/paste attempts</span></div>
                <div><strong>{proctoring.devtoolsAttempts}</strong><span>DevTools attempts</span></div>
                <div><strong>{proctoring.multipleFaces}</strong><span>Multi-face events</span></div>
                <div><strong>{proctoring.riskLevel}</strong><span>Integrity risk</span></div>
              </div>
            </div>
          ) : (
            <div className="next-steps-card">
              <strong>What happens next?</strong>
              <p>The recruiter will review your engagement analysis, behavioral scores, and answers. You'll be contacted about next steps via your registered details.</p>
            </div>
          )}

          <button onClick={handleSignOut}>
            Logout →
          </button>
        </div>
      )}
    </div>
  );
}
