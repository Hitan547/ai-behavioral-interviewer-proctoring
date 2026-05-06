import { Download, Eye, Play, RefreshCw, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiClient } from "../api/client";
import type { AuthSession } from "../auth/useAuthSession";
import type { Candidate, Job, ScoringResult } from "../api/types";

type Props = {
  auth: AuthSession;
};

type PerQuestion = {
  questionIndex: number;
  question: string;
  answered: boolean;
  score: number;
  verdict: string;
  summary: string;
  method?: string;
  dimensions?: {
    clarity: number;
    relevance: number;
    starQuality: number;
    specificity: number;
    communication: number;
    jobFit: number;
  };
  keyStrength?: string;
  keyImprovement?: string;
  recruiterVerdict?: string;
};

type IntegrityRisk = {
  level: string;
  scorePenalty: number;
  tabSwitches: number;
  fullscreenExits: number;
  copyPasteAttempts: number;
  devtoolsAttempts: number;
  faceNotDetected?: number;
  multipleFaces?: number;
  eventCount: number;
};

type DetailedResult = ScoringResult & {
  perQuestion?: PerQuestion[];
  integrityRisk: IntegrityRisk;
};

function verdictClass(verdict: string): string {
  if (verdict === "Strong") return "strong";
  if (verdict === "Needs Review") return "review";
  if (verdict === "Weak") return "weak";
  return "missing";
}

export function RecruiterDashboard({ auth }: Props) {
  const api = useMemo(() => new ApiClient(auth), [auth]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [result, setResult] = useState<DetailedResult | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [jobForm, setJobForm] = useState({ title: "", jdText: "", minPassScore: 60 });
  const [candidateForm, setCandidateForm] = useState({ name: "", email: "" });
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setMessage("");
    try {
      await action();
      setMessage(`${label} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy("");
    }
  }

  async function refreshJobs() {
    const payload = await api.listJobs();
    setJobs(payload.jobs);
    if (!selectedJobId && payload.jobs[0]) {
      setSelectedJobId(payload.jobs[0].jobId);
    }
  }

  async function refreshCandidates(jobId = selectedJobId) {
    if (!jobId) return;
    const payload = await api.listCandidates(jobId);
    setCandidates(payload.candidates);
    if (!selectedCandidateId && payload.candidates[0]) {
      setSelectedCandidateId(payload.candidates[0].candidateId);
    }
  }

  // Generate a candidate interview link
  function candidateLink(): string {
    if (!selectedJobId || !selectedCandidateId) return "";
    const base = window.location.origin + window.location.pathname;
    return `${base}?mode=candidate&jobId=${selectedJobId}&candidateId=${selectedCandidateId}`;
  }

  return (
    <div className="grid two">
      <section className="panel">
        <div className="panel-title">
          <h3>Jobs</h3>
          <button className="icon-button" onClick={() => run("Refresh jobs", refreshJobs)} aria-label="Refresh jobs">
            <RefreshCw size={18} />
          </button>
        </div>
        <div className="form-grid">
          <input
            placeholder="Job title"
            value={jobForm.title}
            onChange={(event) => setJobForm({ ...jobForm, title: event.target.value })}
          />
          <textarea
            placeholder="Job description"
            value={jobForm.jdText}
            onChange={(event) => setJobForm({ ...jobForm, jdText: event.target.value })}
          />
          <input
            type="number"
            min={0}
            max={100}
            value={jobForm.minPassScore}
            onChange={(event) => setJobForm({ ...jobForm, minPassScore: Number(event.target.value) })}
          />
          <button onClick={() => run("Create job", async () => {
            await api.createJob(jobForm);
            await refreshJobs();
          })}>
            Create job
          </button>
        </div>

        <select value={selectedJobId} onChange={(event) => {
          setSelectedJobId(event.target.value);
          setResult(null);
          void run("Load candidates", () => refreshCandidates(event.target.value));
        }}>
          <option value="">Select job</option>
          {jobs.map((job) => (
            <option key={job.jobId} value={job.jobId}>{job.title}</option>
          ))}
        </select>
      </section>

      <section className="panel">
        <div className="panel-title">
          <h3>Candidates</h3>
          <button className="icon-button" onClick={() => run("Refresh candidates", () => refreshCandidates())} aria-label="Refresh candidates">
            <RefreshCw size={18} />
          </button>
        </div>
        <div className="form-grid">
          <input placeholder="Candidate name" value={candidateForm.name} onChange={(event) => setCandidateForm({ ...candidateForm, name: event.target.value })} />
          <input placeholder="Candidate email" value={candidateForm.email} onChange={(event) => setCandidateForm({ ...candidateForm, email: event.target.value })} />
          <label className="file-input">
            <span>📄</span>
            <input type="file" accept="application/pdf" onChange={(event) => setResumeFile(event.target.files?.[0] ?? null)} />
            {resumeFile?.name ?? "Resume PDF"}
          </label>
          <button disabled={!selectedJobId || !resumeFile} onClick={() => run("Create candidate", async () => {
            if (!resumeFile) return;
            const created = await api.createCandidate(selectedJobId, { ...candidateForm, resumeFilename: resumeFile.name });
            await api.uploadResume(created.resumeUpload, resumeFile);
            setSelectedCandidateId(created.candidate.candidateId);
            await refreshCandidates();
          })}>
            Create + upload
          </button>
        </div>

        <div className="list">
          {candidates.map((candidate) => (
            <button
              key={candidate.candidateId}
              className={candidate.candidateId === selectedCandidateId ? "row selected" : "row"}
              onClick={() => {
                setSelectedCandidateId(candidate.candidateId);
                setResult(null);
              }}
            >
              <span>{candidate.name}</span>
              <small>{candidate.interviewStatus}</small>
            </button>
          ))}
        </div>

        {/* Candidate interview link */}
        {selectedJobId && selectedCandidateId && (
          <div style={{ marginTop: 12, fontSize: 12, color: "#697780" }}>
            <strong>Interview link:</strong>{" "}
            <a href={candidateLink()} target="_blank" rel="noopener noreferrer" style={{ color: "#146c63", wordBreak: "break-all" }}>
              {candidateLink()}
            </a>
          </div>
        )}
      </section>

      <section className="panel wide">
        <div className="panel-title">
          <h3>Interview Workflow</h3>
          <p>{busy || message || "Ready"}</p>
        </div>
        <div className="actions">
          <button disabled={!selectedJobId || !selectedCandidateId} onClick={() => run("Prepare interview", async () => {
            await api.prepareInterview(selectedJobId, selectedCandidateId);
            await refreshCandidates();
          })}>
            <Sparkles size={17} />
            Prepare
          </button>
          <button disabled={!selectedJobId || !selectedCandidateId} onClick={() => run("Start scoring", async () => {
            await api.startScoring(selectedJobId, selectedCandidateId);
          })}>
            <Play size={17} />
            Score
          </button>
          <button disabled={!selectedJobId || !selectedCandidateId} onClick={() => run("Load result", async () => {
            const payload = await api.getResult(selectedJobId, selectedCandidateId);
            setResult(payload.result as DetailedResult);
          })}>
            <RefreshCw size={17} />
            Result
          </button>
          {result?.reportDownload && (
            <a className="button-link" href={result.reportDownload.url}>
              <Download size={17} />
              PDF
            </a>
          )}
          {result && (
            <button onClick={() => setShowDetails(!showDetails)}>
              <Eye size={17} />
              {showDetails ? "Hide" : "Details"}
            </button>
          )}
        </div>

        {result && (
          <>
            {/* Summary cards */}
            <div className="result">
              <div>
                <span className="metric">{result.finalScore}</span>
                <p>Final score</p>
              </div>
              <div>
                <span className="metric text">{result.recommendation}</span>
                <p>Recommendation</p>
              </div>
              <div>
                <span className="metric text">{result.integrityRisk.level}</span>
                <p>Integrity risk</p>
              </div>
            </div>

            {/* Integrity details */}
            {showDetails && result.integrityRisk && (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: "0 0 6px", fontSize: 14 }}>Proctoring Signals</h4>
                <div className="integrity-detail">
                  <div>
                    <strong>{result.integrityRisk.tabSwitches}</strong>
                    Tab switches
                  </div>
                  <div>
                    <strong>{result.integrityRisk.fullscreenExits}</strong>
                    Fullscreen exits
                  </div>
                  <div>
                    <strong>{result.integrityRisk.copyPasteAttempts}</strong>
                    Copy/paste
                  </div>
                  <div>
                    <strong>{result.integrityRisk.devtoolsAttempts}</strong>
                    DevTools
                  </div>
                  <div>
                    <strong>{result.integrityRisk.faceNotDetected ?? 0}</strong>
                    Face absent
                  </div>
                  <div>
                    <strong>{result.integrityRisk.multipleFaces ?? 0}</strong>
                    Multiple faces
                  </div>
                </div>
              </div>
            )}

            {/* Per-question breakdown */}
            {showDetails && result.perQuestion && (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: "0 0 6px", fontSize: 14 }}>Per-Question Breakdown</h4>
                <div className="per-question-list">
                  {result.perQuestion.map((pq) => (
                    <div key={pq.questionIndex} className="per-question-item">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <h4>Q{pq.questionIndex + 1}: {pq.question}</h4>
                        <span className={`verdict-pill ${verdictClass(pq.verdict)}`}>{pq.verdict}</span>
                      </div>
                      <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 4 }}>
                        <span style={{ fontSize: 22, fontWeight: 800, color: "#146c63" }}>{pq.score}</span>
                        <span style={{ fontSize: 12, color: "#697780" }}>/ 100 • {pq.method === "llm" ? "AI Scored" : pq.method === "heuristic" ? "Heuristic" : "—"}</span>
                      </div>
                      {pq.summary && <p>{pq.summary}</p>}
                      {pq.dimensions && (
                        <div className="score-dimensions">
                          {Object.entries(pq.dimensions).map(([key, val]) => (
                            <div key={key} className="dimension-card">
                              <span className="dim-score">{val as number}</span>
                              <span className="dim-label">{key.replace(/([A-Z])/g, " $1").trim()}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {pq.keyStrength && pq.keyStrength !== "N/A" && (
                        <p><strong>Strength:</strong> {pq.keyStrength}</p>
                      )}
                      {pq.keyImprovement && pq.keyImprovement !== "N/A" && (
                        <p><strong>Improve:</strong> {pq.keyImprovement}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
