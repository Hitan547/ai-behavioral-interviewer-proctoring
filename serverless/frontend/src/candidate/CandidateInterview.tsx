import { CheckCircle2, Clock3, Eye, EyeOff, Mic, RotateCcw, Send, ShieldCheck, Square, UploadCloud, Video } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiClient } from "../api/client";
import type { PreparedQuestion } from "../api/types";
import type { AuthSession } from "../auth/useAuthSession";
import { useIntegritySignals } from "./integritySignals";
import { useProctoring } from "./useProctoring";
import { useAudioRecorder } from "./useAudioRecorder";

type Props = {
  auth: AuthSession;
};

type InterviewStep = "setup" | "consent" | "device-check" | "interview" | "review" | "submitted";

const QUESTION_SECONDS = 120;

export function CandidateInterview({ auth }: Props) {
  const api = useMemo(() => new ApiClient(auth), [auth]);
  const params = new URLSearchParams(window.location.search);
  const [jobId, setJobId] = useState(params.get("jobId") ?? "");
  const [candidateId, setCandidateId] = useState(params.get("candidateId") ?? "");
  const [questions, setQuestions] = useState<PreparedQuestion[]>([]);
  const [candidateName, setCandidateName] = useState("");
  const [step, setStep] = useState<InterviewStep>("setup");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [answerDurations, setAnswerDurations] = useState<Record<number, number>>({});
  const [answerAudioKeys, setAnswerAudioKeys] = useState<Record<number, string>>({});
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [timeLeft, setTimeLeft] = useState(QUESTION_SECONDS);
  const [message, setMessage] = useState("");
  const mediaStream = useRef<MediaStream | null>(null);

  // Proctoring: browser-side face detection
  const proctoring = useProctoring(questionIndex);

  // Integrity signals: merge browser events + proctoring events
  const integrity = useIntegritySignals(questionIndex, proctoring.events);

  const audio = useAudioRecorder();

  const current = questions[questionIndex];
  const answeredCount = questions.filter((question) => (answers[question.questionIndex] ?? "").trim()).length;
  const progress = questions.length ? Math.round((answeredCount / questions.length) * 100) : 0;

  useEffect(() => {
    if (step !== "interview" || !current) return;
    setTimeLeft(QUESTION_SECONDS);
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      setTimeLeft(Math.max(0, QUESTION_SECONDS - elapsed));
      setAnswerDurations((existing) => ({
        ...existing,
        [current.questionIndex]: Math.min(QUESTION_SECONDS, elapsed),
      }));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [current, step]);

  useEffect(() => {
    return () => {
      mediaStream.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function loadInterview() {
    setMessage("");
    try {
      const payload = await api.getCandidateInterview(jobId, candidateId);
      setQuestions(payload.interview.questions);
      setCandidateName(payload.interview.candidateName);
      setQuestionIndex(0);
      setAnswers({});
      setAnswerDurations({});
      setAnswerAudioKeys({});
      setStep("consent");
      setMessage("Interview loaded.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function checkDevices() {
    setMessage("");
    try {
      // Start proctoring camera
      await proctoring.startCamera();
      setStep("interview");
      setMessage("Camera active — proctoring enabled.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function updateAnswer(value: string) {
    if (!current) return;
    setAnswers({ ...answers, [current.questionIndex]: value });
  }

  function retryCurrentAnswer() {
    if (!current) return;
    setAnswers({ ...answers, [current.questionIndex]: "" });
    setAnswerDurations({ ...answerDurations, [current.questionIndex]: 0 });
    setAnswerAudioKeys({ ...answerAudioKeys, [current.questionIndex]: "" });
    audio.clear();
    setTimeLeft(QUESTION_SECONDS);
  }

  async function uploadAndTranscribeCurrentAudio() {
    if (!current || !audio.recording) return;
    setMessage("");
    try {
      const created = await api.createAudioUpload(jobId, candidateId, {
        questionIndex: current.questionIndex,
        contentType: audio.recording.contentType.split(";")[0] || "audio/webm",
      });
      await api.uploadAudio(created.audioUpload, audio.recording.blob);
      const transcribed = await api.transcribeQuestionAudio(jobId, candidateId, current.questionIndex, {
        audioS3Bucket: created.audioUpload.bucket,
        audioS3Key: created.audioUpload.key,
        contentType: audio.recording.contentType.split(";")[0] || "audio/webm",
      });
      setAnswers({ ...answers, [current.questionIndex]: transcribed.transcription.transcript });
      setAnswerDurations({ ...answerDurations, [current.questionIndex]: audio.recording.durationSeconds });
      setAnswerAudioKeys({ ...answerAudioKeys, [current.questionIndex]: created.audioUpload.key });
      setMessage("Audio uploaded and transcribed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function goNext() {
    if (questionIndex >= questions.length - 1) {
      setStep("review");
      return;
    }
    setQuestionIndex((value) => value + 1);
  }

  async function submit() {
    setMessage("");
    try {
      await api.submitCandidateInterview(jobId, candidateId, {
        consentAccepted,
        answers: questions.map((question) => ({
          questionIndex: question.questionIndex,
          answerText: answers[question.questionIndex] ?? "",
          durationSeconds: answerDurations[question.questionIndex] ?? 0,
          audioS3Key: answerAudioKeys[question.questionIndex] || undefined,
        })).filter((answer) => answer.answerText.trim()),
        integritySignals: integrity,
      });
      proctoring.stopCamera();
      mediaStream.current?.getTracks().forEach((track) => track.stop());
      setStep("submitted");
      setMessage("Interview submitted successfully.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <section className="panel candidate-panel">
      <div className="panel-title">
        <div>
          <h3>{candidateName || "Candidate Interview"}</h3>
          <p>AI-Proctored interview — browser-side face detection active.</p>
        </div>
        {message && <span className="status-pill">{message}</span>}
      </div>

      <div className="interview-stepper">
        {["setup", "consent", "device-check", "interview", "review", "submitted"].map((name) => (
          <span key={name} className={step === name ? "active" : ""}>{name.replace("-", " ")}</span>
        ))}
      </div>

      {step === "setup" && (
        <>
          <div className="form-grid inline">
            <input placeholder="Job ID" value={jobId} onChange={(event) => setJobId(event.target.value)} />
            <input placeholder="Candidate ID" value={candidateId} onChange={(event) => setCandidateId(event.target.value)} />
            <button onClick={loadInterview}>Load questions</button>
          </div>
          <div className="empty-state">
            <CheckCircle2 size={28} />
            <p>Load the prepared interview to begin the candidate flow.</p>
          </div>
        </>
      )}

      {step === "consent" && (
        <div className="gate-card">
          <ShieldCheck size={32} />
          <h3>Consent Required</h3>
          <p>
            This interview uses <strong>AI-assisted proctoring</strong> with browser-based face detection,
            integrity monitoring, and AI scoring. Your camera feed is processed locally in your browser —
            no video is sent to any server.
          </p>
          <label className="consent">
            <input type="checkbox" checked={consentAccepted} onChange={(event) => setConsentAccepted(event.target.checked)} />
            I understand and consent to the AI-proctored interview analysis.
          </label>
          <button disabled={!consentAccepted} onClick={() => setStep("device-check")}>Continue</button>
        </div>
      )}

      {step === "device-check" && (
        <div className="device-check">
          <div className="device-card">
            <Video size={24} />
            <h3>Camera Check</h3>
            <p>Your camera will be used for face detection proctoring. Video stays in your browser — never uploaded.</p>
          </div>
          <div className="device-card">
            <Mic size={24} />
            <h3>Microphone Check</h3>
            <p>Optional: record voice answers. Audio is uploaded only when you click "Upload + transcribe".</p>
          </div>
          <p className="device-status">
            {proctoring.cameraActive
              ? `✅ Camera active — ${proctoring.faceDetected ? "face detected" : "no face detected"}`
              : "Camera not started yet."}
          </p>
          <div className="actions">
            <button onClick={checkDevices}>
              <Video size={17} />
              Start camera + proctoring
            </button>
            <button onClick={() => setStep("interview")}>Continue without camera</button>
          </div>
        </div>
      )}

      {step === "interview" && current && (
        <div className="question-workspace">
          {/* Proctoring status bar */}
          <div className="proctoring-bar">
            <div className="proctoring-status">
              {proctoring.cameraActive ? (
                <span className={`proctoring-indicator ${proctoring.faceDetected ? "ok" : "warning"}`}>
                  {proctoring.faceDetected ? <Eye size={14} /> : <EyeOff size={14} />}
                  {proctoring.faceDetected
                    ? proctoring.faceCount === 1
                      ? "Face detected"
                      : `${proctoring.faceCount} faces detected`
                    : "No face detected"}
                </span>
              ) : (
                <span className="proctoring-indicator off">Camera off</span>
              )}
              <span className="proctoring-events">{integrity.events.length} signal(s)</span>
            </div>
            {/* Camera preview */}
            {proctoring.cameraActive && (
              <div className="camera-preview">
                <video ref={proctoring.videoRef} autoPlay muted playsInline style={{ display: "none" }} />
                <canvas ref={proctoring.canvasRef} />
              </div>
            )}
          </div>

          <div className="question-header">
            <span>Question {questionIndex + 1} of {questions.length}</span>
            <span>{answeredCount}/{questions.length} answered</span>
          </div>
          <div className="timer-row">
            <div>
              <Clock3 size={18} />
              <strong>{Math.floor(timeLeft / 60)}:{String(timeLeft % 60).padStart(2, "0")}</strong>
            </div>
            <progress value={QUESTION_SECONDS - timeLeft} max={QUESTION_SECONDS} />
          </div>
          <h3>{current.question}</h3>
          <div className="audio-card">
            <div>
              <Mic size={20} />
              <span>{audio.isRecording ? "Recording answer..." : audio.recording ? `${audio.recording.durationSeconds}s recorded` : "Voice answer"}</span>
            </div>
            <div className="actions">
              {!audio.isRecording ? (
                <button onClick={audio.start}>
                  <Mic size={17} />
                  Record
                </button>
              ) : (
                <button onClick={audio.stop}>
                  <Square size={17} />
                  Stop
                </button>
              )}
              <button disabled={!audio.recording} onClick={uploadAndTranscribeCurrentAudio}>
                <UploadCloud size={17} />
                Upload + transcribe
              </button>
            </div>
            {audio.error && <p>{audio.error}</p>}
            {answerAudioKeys[current.questionIndex] && <p>Audio saved: {answerAudioKeys[current.questionIndex]}</p>}
          </div>
          <textarea
            value={answers[current.questionIndex] ?? ""}
            placeholder="Record and transcribe, or type your answer here"
            onChange={(event) => updateAnswer(event.target.value)}
          />
          <div className="actions">
            <button disabled={questionIndex === 0} onClick={() => setQuestionIndex((value) => value - 1)}>Previous</button>
            <button onClick={retryCurrentAnswer}>
              <RotateCcw size={17} />
              Retry
            </button>
            <button onClick={goNext}>{questionIndex >= questions.length - 1 ? "Review" : "Next"}</button>
          </div>
        </div>
      )}

      {step === "review" && (
        <div className="review-card">
          <h3>Review Answers</h3>
          <p>{answeredCount} of {questions.length} questions answered. Progress: {progress}%.</p>
          <div className="answer-review-list">
            {questions.map((question) => (
              <button key={question.questionIndex} className="row" onClick={() => {
                setQuestionIndex(question.questionIndex);
                setStep("interview");
              }}>
                <span>Q{question.questionIndex + 1}: {question.question}</span>
                <small>{answers[question.questionIndex]?.trim() ? "Answered" : "Missing"}</small>
              </button>
            ))}
          </div>
          <div className="actions">
            <button onClick={() => setStep("interview")}>Back to interview</button>
            <button disabled={!consentAccepted || answeredCount === 0} onClick={submit}>
              <Send size={17} />
              Submit
            </button>
          </div>
        </div>
      )}

      {step === "submitted" && (
        <div className="completion-card">
          <CheckCircle2 size={28} />
          <h3>Interview Submitted</h3>
          <p>Your answers were submitted successfully. The recruiter can now start scoring and review the report.</p>
          <div className="result">
            <div>
              <span className="metric">{answeredCount}</span>
              <p>Answers</p>
            </div>
            <div>
              <span className="metric text">{integrity.events.length}</span>
              <p>Integrity events</p>
            </div>
            <div>
              <span className="metric text">
                {proctoring.faceNotDetectedCount + proctoring.multipleFacesCount > 0
                  ? `${proctoring.faceNotDetectedCount + proctoring.multipleFacesCount} flags`
                  : "Clean"}
              </span>
              <p>Proctoring</p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
