import { Download, FileUp, Play, RefreshCw, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiClient } from "../api/client";
import type { AuthSession } from "../auth/useAuthSession";
import type { Candidate, Job, ScoringResult } from "../api/types";

type Props = {
  auth: AuthSession;
};

export function RecruiterDashboard({ auth }: Props) {
  const api = useMemo(() => new ApiClient(auth), [auth]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [result, setResult] = useState<ScoringResult | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [jobForm, setJobForm] = useState({ title: "", jdText: "", minPassScore: 60 });
  const [candidateForm, setCandidateForm] = useState({ name: "", email: "" });
  const [resumeFile, setResumeFile] = useState<File | null>(null);

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
            <FileUp size={18} />
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
            setResult(payload.result);
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
        </div>

        {result && (
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
        )}
      </section>
    </div>
  );
}
