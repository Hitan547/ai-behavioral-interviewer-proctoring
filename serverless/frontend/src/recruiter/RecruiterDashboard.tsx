import {
  AlertTriangle, ArrowLeft, BarChart3, BriefcaseBusiness, CheckCircle2,
  ChevronDown, ChevronRight, ClipboardList, CreditCard, Download, Eye, FileText,
  Mail, MessageSquareText, Play, RefreshCw, Search, ShieldCheck,
  Sparkles, Upload, Users
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiClient } from "../api/client";
import type { AuthSession } from "../auth/useAuthSession";
import type { BillingSummary, Candidate, Job, MatchResult, ScoringResult } from "../api/types";
import { BillingPanel } from "./BillingPanel";

type Props = { auth: AuthSession };
type NavTab = "candidates" | "jobs" | "analytics" | "billing";
type JobStep = "details" | "resumes" | "shortlist";
type SortBy = "date" | "name" | "score" | "status";

type PerQuestion = {
  questionIndex: number; question: string; answered: boolean;
  answerText?: string; score: number; verdict: string; summary: string; method?: string;
  dimensions?: { clarity: number; relevance: number; starQuality: number; specificity: number; communication: number; jobFit: number };
  keyStrength?: string; keyImprovement?: string; recruiterVerdict?: string; starDetected?: boolean;
};
type IntegrityRisk = {
  level: string; scorePenalty: number; tabSwitches: number; fullscreenExits: number;
  copyPasteAttempts: number; devtoolsAttempts: number;
  faceNotDetected?: number; multipleFaces?: number; eventCount: number;
};
type DetailedResult = ScoringResult & { perQuestion?: PerQuestion[]; integrityRisk: IntegrityRisk };
type RecommendedCandidate = {
  candidate: Candidate;
  job?: Job;
  normalizedScore: number;
  displayScore: string;
  thresholdLabel: string;
  signal: string;
};

function verdictClass(v: string) {
  if (v === "Strong") return "strong";
  if (v === "Needs Review") return "review";
  if (v === "Weak") return "weak";
  return "missing";
}

// ── Demo data for demo mode ──
const DEMO_JOBS: Job[] = [
  { orgId: "demo", jobId: "j1", title: "Python Backend Developer", jdText: "FastAPI, PostgreSQL, AWS Lambda", minPassScore: 60, openPositions: 3, shortlistThreshold: 7, status: "Active", deadline: "2026-06-15" },
  { orgId: "demo", jobId: "j2", title: "React Frontend Engineer", jdText: "React, TypeScript, Vite", minPassScore: 65, openPositions: 2, shortlistThreshold: 7, status: "Active", deadline: "2026-06-30" },
];
const DEMO_CANDIDATES: Record<string, Candidate[]> = {
  j1: [
    { orgId: "demo", jobId: "j1", candidateId: "c1", name: "Priya Sharma", email: "priya@example.com", collegeName: "MIT Campus", department: "CSE", graduationYear: "2026", matchScore: 8.5, matchReason: "Strong Python + AWS experience", latestResultScore: 82, latestAssessmentStatus: "Passed", interviewStatus: "Scored" },
    { orgId: "demo", jobId: "j1", candidateId: "c2", name: "Arjun Patel", email: "arjun@example.com", collegeName: "IIT Campus", department: "AI/ML", graduationYear: "2026", matchScore: 7.2, matchReason: "Good backend skills, limited AWS", interviewStatus: "Invited" },
    { orgId: "demo", jobId: "j1", candidateId: "c3", name: "Sneha Reddy", email: "sneha@example.com", collegeName: "BITS Campus", department: "IT", graduationYear: "2025", matchScore: 9.1, matchReason: "Excellent full-stack match", latestResultScore: 76, latestAssessmentStatus: "Passed", interviewStatus: "Scored" },
    { orgId: "demo", jobId: "j1", candidateId: "c4", name: "Rohit Kumar", email: "rohit@example.com", collegeName: "MIT Campus", department: "ECE", graduationYear: "2026", matchScore: 5.4, matchReason: "Partial skill overlap", interviewStatus: "Expired" },
    { orgId: "demo", jobId: "j1", candidateId: "c5", name: "Ananya Iyer", email: "ananya@example.com", collegeName: "IIT Campus", department: "CSE", graduationYear: "2026", matchScore: 7.8, matchReason: "Strong Python, learning AWS", interviewStatus: "In Progress" },
  ],
  j2: [
    { orgId: "demo", jobId: "j2", candidateId: "c6", name: "Vikram Singh", email: "vikram@example.com", collegeName: "NIT Campus", department: "CSE", graduationYear: "2026", matchScore: 6.8, matchReason: "React experience, needs TypeScript", interviewStatus: "Invited" },
    { orgId: "demo", jobId: "j2", candidateId: "c7", name: "Meera Nair", email: "meera@example.com", collegeName: "BITS Campus", department: "CSE", graduationYear: "2025", matchScore: 8.9, matchReason: "Expert React + TypeScript", latestResultScore: 79, latestAssessmentStatus: "Passed", interviewStatus: "Scored" },
  ],
};

const allDemoCandidates = () => Object.values(DEMO_CANDIDATES).flat();

function activityTime(candidate: Candidate) {
  return candidate.latestResultAt || candidate.submittedAt || candidate.startedAt || candidate.inviteSentAt || shortlistedTime(candidate) || 0;
}

function shortlistedTime(candidate: Candidate) {
  return candidate.shortlistedAt || 0;
}

function formatShortDate(epoch?: number) {
  if (!epoch) return "";
  return new Date(epoch * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function jobOptionLabel(job: Job) {
  const date = formatShortDate(job.createdAt || job.updatedAt);
  const suffix = job.jobId ? job.jobId.slice(0, 6) : "";
  return [job.title, date || suffix ? `${date || "job"} ${suffix}` : ""].filter(Boolean).join(" - ");
}

function candidateSourceLabel(candidate: Pick<Candidate, "collegeName" | "department" | "graduationYear">) {
  return [candidate.collegeName, candidate.department, candidate.graduationYear].filter(Boolean).join(" - ");
}

function clamp10(value: number) {
  return Math.max(0, Math.min(10, Math.round(value * 10) / 10));
}

function scoreTone(score: number) {
  if (score >= 75) return "strong";
  if (score >= 55) return "advance";
  if (score >= 35) return "review";
  return "weak";
}

function scoreLabel(score: number) {
  if (score >= 75) return "Strong Advance";
  if (score >= 55) return "Advance";
  if (score >= 35) return "Needs Review";
  return "Do Not Advance";
}

function answerScoreFor(result: DetailedResult) {
  return result.baseScore ?? result.finalScore;
}

function decisionFor(result: DetailedResult) {
  const risk = result.integrityRisk?.level || "Low";
  const answerScore = answerScoreFor(result);
  if (result.assessmentStatus === "Review Required") {
    return {
      label: "Review Required",
      note: "Answer score meets the role threshold, but proctoring signals need human review.",
      next: "Review camera/face signals, transcript quality, and any candidate context before deciding.",
      tone: "review",
    };
  }
  if (result.finalScore >= 75 && !["High", "Critical"].includes(risk)) {
    return {
      label: "Advance",
      note: "Candidate looks suitable for the next hiring step.",
      next: "Shortlist or schedule the next round.",
      tone: "strong",
    };
  }
  if (result.finalScore < 50 || (["High", "Critical"].includes(risk) && answerScore < (result.minPassScore ?? 60))) {
    return {
      label: "Hold",
      note: "Review answers and proctoring context before deciding.",
      next: "Check the transcript, integrity signals, and role context before moving forward.",
      tone: "review",
    };
  }
  return {
    label: "Review",
    note: "Candidate has usable signal but needs recruiter judgement.",
    next: "Compare against the JD and other candidates before deciding.",
    tone: "advance",
  };
}

function reportStrengths(result: DetailedResult) {
  const strengths = (result.perQuestion || [])
    .map((item) => item.keyStrength)
    .filter((value): value is string => Boolean(value && value !== "N/A"))
    .slice(0, 3);
  if (strengths.length) return strengths;
  const answerScore = answerScoreFor(result);
  if (answerScore >= 75) return ["Strong answer quality across the interview."];
  if (answerScore >= 55) return ["Several answers show relevant role signal."];
  return ["The interview was completed and can be manually reviewed."];
}

function reportConcerns(result: DetailedResult) {
  const concerns = (result.perQuestion || [])
    .map((item) => item.keyImprovement)
    .filter((value): value is string => Boolean(value && value !== "N/A"))
    .slice(0, 3);
  if (["High", "Critical"].includes(result.integrityRisk?.level || "")) {
    concerns.unshift(`${result.integrityRisk.level} proctoring risk needs review.`);
  }
  if (concerns.length) return concerns.slice(0, 3);
  if (result.finalScore < 55) return ["Answer depth or relevance may be below the role threshold."];
  return ["No major concern detected from the stored report."];
}

function questionSignals(item: PerQuestion, riskPenalty: number) {
  const dimensions = item.dimensions;
  const answerQuality = clamp10(item.score / 10);
  const delivery = clamp10(dimensions?.communication ?? Math.max(0, answerQuality - 1));
  const attentiveness = clamp10(Math.max(0, 10 - riskPenalty / 2));
  return { answerQuality, delivery, attentiveness };
}

function candidateMatchesStatus(candidate: Candidate, status: string) {
  if (status === "All") return true;
  if (status === "Shortlisted") return Boolean(candidate.shortlisted) || candidate.interviewStatus === "Shortlisted";
  if (status === "Passed") return candidate.latestAssessmentStatus === "Passed" || candidate.interviewStatus === "Passed";
  if (status === "Review Required") {
    return candidate.latestAssessmentStatus === "Review Required" || candidate.latestRecommendation === "Manual Review Required";
  }
  if (status === "Below Threshold") {
    return candidate.latestAssessmentStatus === "Below Threshold" || candidate.interviewStatus === "Below Threshold";
  }
  return candidate.interviewStatus === status;
}

const RETEST_ELIGIBLE_STATUSES = new Set([
  "Completed",
  "Interview Submitted",
  "Scored",
  "Passed",
  "Below Threshold",
  "Review Required",
]);

function canAllowRetest(candidate: Candidate) {
  return Boolean(candidate.latestSubmissionId)
    || typeof candidate.latestResultScore === "number"
    || RETEST_ELIGIBLE_STATUSES.has(candidate.interviewStatus);
}

function openPositionsForJob(job?: Job) {
  const value = Number(job?.openPositions ?? 10);
  if (!Number.isFinite(value)) return 10;
  return Math.max(1, Math.min(20, Math.round(value)));
}

function recommendedCandidate(candidate: Candidate, job?: Job): RecommendedCandidate | null {
  if (candidate.interviewStatus === "Expired" || candidate.latestRecommendation === "Not Recommended") {
    return null;
  }
  if (candidate.latestAssessmentStatus === "Review Required" || candidate.latestRecommendation === "Manual Review Required") {
    return null;
  }
  if (typeof candidate.latestResultScore === "number") {
    const threshold = job?.minPassScore ?? 60;
    const passed = candidate.latestAssessmentStatus
      ? candidate.latestAssessmentStatus === "Passed"
      : candidate.latestResultScore >= threshold;
    if (!passed) return null;
    return {
      candidate,
      job,
      normalizedScore: candidate.latestResultScore,
      displayScore: `${candidate.latestResultScore}/100`,
      thresholdLabel: `${threshold}/100`,
      signal: "Interview score",
    };
  }
  return null;
}

function rankRecommendedCandidates(candidates: Candidate[], jobById: Map<string, Job>) {
  const groups = new Map<string, RecommendedCandidate[]>();
  for (const candidate of candidates) {
    const item = recommendedCandidate(candidate, jobById.get(candidate.jobId));
    if (!item) continue;
    const group = groups.get(candidate.jobId) || [];
    group.push(item);
    groups.set(candidate.jobId, group);
  }
  return Array.from(groups.entries()).flatMap(([jobId, items]) => {
    const job = jobById.get(jobId);
    return items
      .sort((a, b) => b.normalizedScore - a.normalizedScore || activityTime(b.candidate) - activityTime(a.candidate))
      .slice(0, openPositionsForJob(job));
  }).sort((a, b) => (
    (a.job?.title || "").localeCompare(b.job?.title || "")
    || b.normalizedScore - a.normalizedScore
  ));
}

function csvCell(value: string | number | undefined | null) {
  const text = value === undefined || value === null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function safeFilenamePart(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "all-jobs";
}

function TrendChart({ result }: { result: DetailedResult }) {
  const points = (result.perQuestion || []).slice(0, 8);
  if (!points.length) return null;
  const width = 720;
  const height = 220;
  const left = 42;
  const right = 20;
  const top = 18;
  const bottom = 34;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const x = (index: number) => left + (points.length === 1 ? chartWidth / 2 : (index / (points.length - 1)) * chartWidth);
  const y = (value: number) => top + chartHeight - (value / 10) * chartHeight;
  const series = [
    { key: "answerQuality", label: "Answer Quality", color: "#3b82f6" },
    { key: "delivery", label: "Delivery Signal", color: "#f59e0b" },
    { key: "attentiveness", label: "Attentiveness", color: "#10b981" },
  ] as const;
  const values = points.map((point) => questionSignals(point, result.integrityRisk?.scorePenalty || 0));

  return (
    <div className="report-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Question score trend">
        {[0, 5, 10].map((tick) => (
          <g key={tick}>
            <line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} />
            <text x={left - 12} y={y(tick) + 4}>{tick}</text>
          </g>
        ))}
        {series.map((line) => {
          const path = values.map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(point[line.key])}`).join(" ");
          return (
            <g key={line.key}>
              <path d={path} stroke={line.color} />
              {values.map((point, index) => (
                <circle key={`${line.key}-${index}`} cx={x(index)} cy={y(point[line.key])} r="4" fill={line.color} />
              ))}
            </g>
          );
        })}
        {points.map((point, index) => (
          <text key={point.questionIndex} className="axis-label" x={x(index)} y={height - 8}>Q{index + 1}</text>
        ))}
      </svg>
      <div className="chart-legend">
        {series.map((line) => <span key={line.key}><i style={{ background: line.color }} />{line.label}</span>)}
      </div>
    </div>
  );
}

function CandidateFullReport({
  candidate,
  job,
  result,
  expandedQuestion,
  onToggleQuestion,
  onBack,
}: {
  candidate: Candidate;
  job?: Job;
  result: DetailedResult;
  expandedQuestion: number | null;
  onToggleQuestion: (index: number) => void;
  onBack: () => void;
}) {
  const decision = decisionFor(result);
  const strengths = reportStrengths(result);
  const concerns = reportConcerns(result);
  const risk = result.integrityRisk || { level: "Low", scorePenalty: 0, tabSwitches: 0, fullscreenExits: 0, copyPasteAttempts: 0, devtoolsAttempts: 0, eventCount: 0 };
  const answerScore = answerScoreFor(result);
  const displayLabel = result.assessmentStatus === "Review Required" ? "Review Required" : scoreLabel(result.finalScore);
  const displayTone = result.assessmentStatus === "Review Required" ? "review" : scoreTone(result.finalScore);

  return (
    <section className="full-report">
      <div className="report-header">
        <button className="secondary-btn back-btn" onClick={onBack}><ArrowLeft size={16} /> Back to candidates</button>
        {result.reportDownload && (
          <a className="button-link report-download" href={result.reportDownload.url}>
            <Download size={17} /> PDF
          </a>
        )}
      </div>

      <div className="report-title-row">
        <div>
          <p className="eyebrow">Candidate Report</p>
          <h3>{candidate.name}</h3>
          <p>{candidate.email} {job?.title ? `• ${job.title}` : ""}</p>
        </div>
        <span className={`report-verdict ${displayTone}`}>{displayLabel}</span>
      </div>

      <div className={`decision-banner ${decision.tone}`}>
        <div>
          <strong>{decision.label}</strong>
          <span>Answer score: {answerScore}/100 - Final score: {result.finalScore}/100 - Recommendation: {result.recommendation}</span>
        </div>
        <div>
          <strong>Proctoring</strong>
          <span>{risk.level}</span>
        </div>
      </div>

      <div className="report-summary-card">
        <div>
          <span className="report-kicker">Decision Summary</span>
          <strong className={decision.tone}>{decision.label}</strong>
          <p>{decision.note}</p>
        </div>
        <div>
          <span className="report-kicker good">Top Strengths</span>
          {strengths.slice(0, 2).map((item) => <p key={item}>{item}</p>)}
        </div>
        <div>
          <span className="report-kicker warn">Main Concerns</span>
          {concerns.slice(0, 2).map((item) => <p key={item}>{item}</p>)}
        </div>
        <div>
          <span className="report-kicker">Next Action</span>
          <p>{decision.next}</p>
        </div>
      </div>

      <div className="report-notice">
        AI scores and proctoring risk indicators are review aids. Review the underlying answers, role context, accessibility needs, and any technical issues before deciding.
      </div>

      <div className="report-metrics">
        <div><span>Answer Score</span><strong>{answerScore}/100</strong></div>
        <div><span>Final Score</span><strong>{result.finalScore}/100</strong></div>
        <div><span>Assessment</span><strong>{result.assessmentStatus || "Reviewed"}</strong></div>
        <div><span>Risk Penalty</span><strong>-{risk.scorePenalty || 0}</strong></div>
        <div><span>Events</span><strong>{risk.eventCount || 0}</strong></div>
      </div>

      <div className="report-section-head">
        <BarChart3 size={22} />
        <h3>Score Trend</h3>
      </div>
      <TrendChart result={result} />

      <div className="report-section-head">
        <ShieldCheck size={22} />
        <h3>Proctoring Signals</h3>
      </div>
      <div className="integrity-detail report-integrity">
        <div><strong>{risk.tabSwitches}</strong>Tab switches</div>
        <div><strong>{risk.fullscreenExits}</strong>Fullscreen exits</div>
        <div><strong>{risk.copyPasteAttempts}</strong>Copy/paste</div>
        <div><strong>{risk.devtoolsAttempts}</strong>DevTools</div>
        <div><strong>{risk.faceNotDetected ?? 0}</strong>Face absent</div>
        <div><strong>{risk.multipleFaces ?? 0}</strong>Multiple faces</div>
      </div>

      <div className="report-section-head">
        <MessageSquareText size={22} />
        <h3>Question Breakdown</h3>
      </div>
      <div className="report-questions">
        {(result.perQuestion || []).map((item, index) => {
          const expanded = expandedQuestion === item.questionIndex;
          const signals = questionSignals(item, risk.scorePenalty || 0);
          return (
            <div className="report-question" key={item.questionIndex}>
              <button className="report-question-toggle" onClick={() => onToggleQuestion(item.questionIndex)}>
                {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                <span>Q{index + 1}: {item.question}</span>
                <em className={`verdict-pill ${verdictClass(item.verdict)}`}>{item.recruiterVerdict || item.verdict}</em>
              </button>
              {expanded && (
                <div className="report-question-body">
                  <strong>Answer</strong>
                  <div className="answer-box">{item.answerText || "Answer text is available for newly scored submissions. Older results may need to be rescored."}</div>
                  <div className="report-metrics small">
                    <div><span>Answer Quality</span><strong>{signals.answerQuality}/10</strong></div>
                    <div><span>Delivery Signal</span><strong>{signals.delivery}/10</strong></div>
                    <div><span>Attentiveness</span><strong>{signals.attentiveness}/10</strong></div>
                    <div><span>Score</span><strong>{item.score}/100</strong></div>
                  </div>
                  {item.dimensions && (
                    <>
                      <strong>Dimension Scores</strong>
                      <div className="score-dimensions report-dimensions">
                        {Object.entries(item.dimensions).map(([key, value]) => (
                          <div key={key} className="dimension-card">
                            <span className="dim-score">{value as number}/10</span>
                            <span className="dim-label">{key.replace(/([A-Z])/g, " $1").trim()}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                  {item.summary && <p className="question-summary">{item.summary}</p>}
                  <div className="report-insight-grid">
                    <div className="insight-good"><CheckCircle2 size={16} /> {item.keyStrength && item.keyStrength !== "N/A" ? item.keyStrength : "Relevant answer signal captured."}</div>
                    <div className="insight-warn"><AlertTriangle size={16} /> {item.keyImprovement && item.keyImprovement !== "N/A" ? item.keyImprovement : "No major improvement note captured."}</div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function demoReport(candidate: Candidate): DetailedResult {
  const score = Math.round((candidate.matchScore || 7.2) * 10);
  const perQuestion = DEMO_QUESTIONS_FOR_REPORT.map((question, index) => ({
    questionIndex: index,
    question,
    answerText: "Demo answer text for recruiter report exploration.",
    answered: true,
    score: Math.max(45, Math.min(92, score - index * 3 + 4)),
    verdict: score >= 75 ? "Strong" : score >= 55 ? "Needs Review" : "Weak",
    summary: "Demo report signal generated from sample dashboard data.",
    method: "heuristic",
    dimensions: {
      clarity: 7,
      relevance: 8,
      starQuality: 6,
      specificity: 7,
      communication: 8,
      jobFit: 7,
    },
    keyStrength: candidate.matchReason || "Relevant role experience.",
    keyImprovement: "Validate details in a recruiter follow-up.",
    recruiterVerdict: score >= 75 ? "Strong Advance" : "Advance",
  }));
  return {
    baseScore: score,
    finalScore: score,
    assessmentStatus: score >= 60 ? "Passed" : "Below Threshold",
    recommendation: score >= 75 ? "Strong Fit" : score >= 55 ? "Needs Review" : "Not Recommended",
    summary: "Demo report preview.",
    integrityRisk: {
      level: "Low",
      scorePenalty: 0,
      tabSwitches: 0,
      fullscreenExits: 0,
      copyPasteAttempts: 0,
      devtoolsAttempts: 0,
      eventCount: 0,
    },
    perQuestion,
  };
}

const DEMO_QUESTIONS_FOR_REPORT = [
  "Tell me about a project where you delivered under deadline pressure.",
  "Describe a technical decision you had to explain to a stakeholder.",
  "Give an example of a production issue you debugged.",
  "How do you prioritize competing engineering tasks?",
  "Describe feedback you received and how you improved.",
];

function demoBillingSummary(
  used: number,
  orgName = "Local Demo Org",
  ownerEmail = "recruiter@talentryx.local",
  provider = "demo",
): BillingSummary {
  const limit = 50;
  return {
    organization: { orgId: provider === "local" ? "local-org" : "demo", orgName, ownerEmail },
    currentPlan: {
      id: "trial",
      name: "Trial",
      priceLabel: "Free pilot",
      amountPaise: 0,
      monthlyInterviewLimit: limit,
      features: ["50 interviews per month", "Candidate reports", "Basic recruiter dashboard", "Proctoring signals"],
      status: "Trial active",
      trialExpiresAt: Math.floor(Date.now() / 1000) + 14 * 24 * 60 * 60,
    },
    usage: {
      used,
      limit,
      remaining: Math.max(0, limit - used),
      currentMonth: new Date().toISOString().slice(0, 7),
      usagePercent: Math.min(100, Math.round((used / limit) * 100)),
    },
    plans: [
      { id: "trial", name: "Trial", priceLabel: "Free pilot", amountPaise: 0, monthlyInterviewLimit: 50, features: ["50 interviews per month", "Candidate reports", "Basic recruiter dashboard", "Proctoring signals"] },
      { id: "starter", name: "Starter", priceLabel: "INR 8,250/mo", amountPaise: 825000, monthlyInterviewLimit: 100, features: ["100 interviews per month", "Multi-user recruiter access", "PDF candidate reports", "Email support"] },
      { id: "pro", name: "Pro", priceLabel: "INR 24,900/mo", amountPaise: 2490000, monthlyInterviewLimit: 500, popular: true, features: ["500 interviews per month", "Advanced analytics", "API and webhook readiness", "Priority support"] },
      { id: "enterprise", name: "Enterprise", priceLabel: "Custom", amountPaise: 0, monthlyInterviewLimit: null, features: ["Custom interview volume", "Dedicated account manager", "Security and procurement support", "Custom integrations"] },
    ],
    events: [{
      eventId: "demo-created",
      eventType: "created",
      label: "Account created",
      newPlan: "trial",
      provider,
      createdAt: Math.floor(Date.now() / 1000),
    }],
    paymentGateway: { provider: "razorpay", configured: false },
  };
}

export function RecruiterDashboard({ auth }: Props) {
  const api = useMemo(() => new ApiClient(auth), [auth]);
  const isDemo = auth.isDemoMode;

  // Nav
  const [tab, setTab] = useState<NavTab>("candidates");

  // Jobs
  const [jobs, setJobs] = useState<Job[]>(isDemo ? DEMO_JOBS : []);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [shortlistJobId, setShortlistJobId] = useState("");
  const [jobStep, setJobStep] = useState<JobStep>("details");
  const [jobForm, setJobForm] = useState({ title: "", jdText: "", minPassScore: 60, openPositions: 10, shortlistThreshold: 7, deadline: "" });
  const [candidateSource, setCandidateSource] = useState({ collegeName: "", department: "", graduationYear: "" });
  const [resumeFiles, setResumeFiles] = useState<File[]>([]);

  // Candidates
  const [candidates, setCandidates] = useState<Candidate[]>(isDemo ? allDemoCandidates() : []);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState("All");
  const [filterCollege, setFilterCollege] = useState("All");
  const [sortBy, setSortBy] = useState<SortBy>("date");

  // Shortlist
  const [matchResults, setMatchResults] = useState<MatchResult[]>([]);

  // Results
  const [result, setResult] = useState<DetailedResult | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [reportCandidate, setReportCandidate] = useState<Candidate | null>(null);
  const [reportResult, setReportResult] = useState<DetailedResult | null>(null);
  const [expandedQuestion, setExpandedQuestion] = useState<number | null>(0);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [lastInvite, setLastInvite] = useState<{ username: string; password: string; interviewUrl: string } | null>(null);
  const [bulkInvites, setBulkInvites] = useState<Array<{
    candidateId: string;
    name: string;
    email: string;
    username: string;
    password: string;
    interviewUrl: string;
    provider?: string;
  }>>([]);
  const [billing, setBilling] = useState<BillingSummary | null>(isDemo ? demoBillingSummary(allDemoCandidates().length) : null);
  const [billingLoading, setBillingLoading] = useState(false);
  const [billingError, setBillingError] = useState("");

  function canUseLocalBillingPreview() {
    return /localhost|127\.0\.0\.1/.test(auth.apiBaseUrl || "") && auth.orgId === "local-org";
  }

  async function run(label: string, action: () => Promise<void | string>) {
    setBusy(label); setMessage("");
    try {
      const nextMessage = await action();
      setMessage(nextMessage || `${label} completed.`);
    }
    catch (e) { setMessage(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(""); }
  }

  async function refreshJobs() {
    if (isDemo) {
      setJobs(DEMO_JOBS);
      return DEMO_JOBS;
    }
    const p = await api.listJobs();
    setJobs(p.jobs);
    return p.jobs;
  }

  async function refreshCandidates(jid = selectedJobId, jobList = jobs) {
    if (isDemo) {
      setCandidates(jid ? (DEMO_CANDIDATES[jid] || []) : allDemoCandidates());
      return;
    }
    if (!jid) {
      const sourceJobs = jobList.length ? jobList : await refreshJobs();
      const results = await Promise.all(sourceJobs.map(async (job) => {
        try {
          const payload = await api.listCandidates(job.jobId);
          return payload.candidates;
        } catch {
          return [];
        }
      }));
      setCandidates(results.flat());
      return;
    }
    const p = await api.listCandidates(jid);
    setCandidates(p.candidates);
  }

  async function refreshBilling() {
    if (isDemo) {
      setBilling(demoBillingSummary(candidates.length));
      setBillingError("");
      return;
    }
    setBillingLoading(true);
    setBillingError("");
    try {
      const payload = await api.getBilling();
      setBilling(payload.billing);
    } catch (error) {
      if (canUseLocalBillingPreview()) {
        setBilling(demoBillingSummary(candidates.length, "Local Dev Org", auth.username || "recruiter@talentryx.local", "local"));
        setBillingError("Showing local billing preview. Restart the local backend to load live DynamoDB billing data.");
      } else {
        setBillingError(error instanceof Error ? error.message : "Billing is temporarily unavailable.");
      }
    } finally {
      setBillingLoading(false);
    }
  }

  function selectJob(jid: string) {
    setSelectedJobId(jid); setResult(null); setSelectedCandidateId("");
    setReportCandidate(null);
    setReportResult(null);
    setLastInvite(null);
    setBulkInvites([]);
    setFilterCollege("All");
    setShortlistJobId("");
    void run("Load candidates", () => refreshCandidates(jid));
  }

  async function openFullReport(candidate: Candidate) {
    setBusy("Load report");
    setMessage("");
    try {
      if (isDemo) {
        const detailed = demoReport(candidate);
        setSelectedCandidateId(candidate.candidateId);
        setResult(detailed);
        setReportCandidate(candidate);
        setReportResult(detailed);
        setExpandedQuestion(0);
        return;
      }
      const payload = await api.getResult(candidate.jobId, candidate.candidateId);
      const detailed = payload.result as DetailedResult;
      setSelectedCandidateId(candidate.candidateId);
      setResult(detailed);
      setReportCandidate(candidate);
      setReportResult(detailed);
      setExpandedQuestion(detailed.perQuestion?.[0]?.questionIndex ?? null);
    } catch (error) {
      const canStartScoring = ["Interview Submitted", "Completed"].includes(candidate.interviewStatus);
      if (!isDemo && canStartScoring) {
        try {
          await api.startScoring(candidate.jobId, candidate.candidateId);
          setMessage("No report was ready yet, so scoring has been started. Refresh in a moment and open Full Report again.");
        } catch {
          setMessage(error instanceof Error ? error.message : "Report is not ready yet.");
        }
      } else {
        setMessage(error instanceof Error ? error.message : "Report is not ready yet.");
      }
    } finally {
      setBusy("");
    }
  }

  async function allowRetestFor(candidate: Candidate) {
    if (!canAllowRetest(candidate)) {
      throw new Error("Retest is only available after a candidate has submitted an interview.");
    }
    if (isDemo) {
      const demoPassword = "TX-DEMO2";
      setCandidates((current) => current.map((item) => (
        item.candidateId === candidate.candidateId && item.jobId === candidate.jobId
          ? { ...item, interviewStatus: "Invited", inviteSentAt: Math.floor(Date.now() / 1000), retestCount: (item.retestCount || 0) + 1 }
          : item
      )));
      setLastInvite({
        username: candidate.email,
        password: demoPassword,
        interviewUrl: `?mode=candidate&orgId=${encodeURIComponent(candidate.orgId)}&jobId=${encodeURIComponent(candidate.jobId)}&candidateId=${encodeURIComponent(candidate.candidateId)}`,
      });
      return `Demo retest credentials prepared for ${candidate.email}.`;
    }
    await api.prepareInterview(candidate.jobId, candidate.candidateId);
    const invite = await api.allowRetest(candidate.jobId, candidate.candidateId);
    setLastInvite({
      username: invite.username || candidate.email,
      password: invite.password || "",
      interviewUrl: invite.interviewUrl,
    });
    setResult(null);
    setReportCandidate(null);
    setReportResult(null);
    await refreshCandidates(selectedJobId);
    await refreshBilling();
    return `Retest invite sent to ${candidate.email}. Previous submissions remain stored for audit review.`;
  }

  useEffect(() => {
    if (isDemo) return;
    void (async () => {
      const loadedJobs = await refreshJobs();
      await refreshCandidates(selectedJobId, loadedJobs);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo]);

  useEffect(() => {
    if (isDemo) return;
    void refreshCandidates(selectedJobId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo, selectedJobId]);

  useEffect(() => {
    if (tab === "billing") void refreshBilling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // Computed
  const jobById = useMemo(() => new Map(jobs.map((job) => [job.jobId, job])), [jobs]);
  const candidateJobTitle = (candidate: Candidate) => jobById.get(candidate.jobId)?.title || "Unknown job";
  const selectedCandidate = candidates.find((candidate) => candidate.candidateId === selectedCandidateId) || null;
  const activeCandidateJobId = selectedCandidate?.jobId || selectedJobId;
  const selectedCandidateCanRetest = selectedCandidate ? canAllowRetest(selectedCandidate) : false;
  const completedStatuses = new Set(["Completed", "Interview Submitted", "Scored", "Passed", "Review Required", "Below Threshold"]);
  const availableColleges = Array.from(new Set(
    candidates.map((candidate) => candidate.collegeName).filter((value): value is string => Boolean(value)),
  )).sort((a, b) => a.localeCompare(b));
  const filteredCandidates = candidates.filter((c) => {
    const query = searchQuery.toLowerCase();
    if (query && !`${c.name} ${c.email} ${candidateSourceLabel(c)} ${candidateJobTitle(c)}`.toLowerCase().includes(query)) return false;
    if (!candidateMatchesStatus(c, filterStatus)) return false;
    if (filterCollege !== "All" && (c.collegeName || "Unassigned") !== filterCollege) return false;
    return true;
  }).sort((a, b) => {
    if (sortBy === "date") return activityTime(b) - activityTime(a);
    if (sortBy === "score") return (b.latestResultScore ?? b.matchScore ?? 0) - (a.latestResultScore ?? a.matchScore ?? 0);
    if (sortBy === "status") return a.interviewStatus.localeCompare(b.interviewStatus);
    return a.name.localeCompare(b.name);
  });
  const recentActivity = candidates
    .filter((candidate) => completedStatuses.has(candidate.interviewStatus) || typeof candidate.latestResultScore === "number")
    .sort((a, b) => activityTime(b) - activityTime(a))
    .slice(0, 4);
  const recommendedShortlist = rankRecommendedCandidates(candidates, jobById);
  const invitedCount = candidates.filter((c) => c.interviewStatus === "Invited").length;
  const startedCount = candidates.filter((c) => c.interviewStatus === "In Progress").length;
  const completedCount = candidates.filter((c) => completedStatuses.has(c.interviewStatus)).length;
  const expiredCount = candidates.filter((c) => c.interviewStatus === "Expired").length;
  const scoredCandidates = candidates.filter((c) => typeof c.latestResultScore === "number");
  const avgScore = scoredCandidates.length
    ? Math.round(scoredCandidates.reduce((total, c) => total + (c.latestResultScore ?? 0), 0) / scoredCandidates.length)
    : null;
  const passedCount = candidates.filter((c) => c.latestAssessmentStatus === "Passed").length;
  const passRate = scoredCandidates.length ? Math.round((passedCount / scoredCandidates.length) * 100) : null;
  const flaggedCount = candidates.filter((c) => (
    ["High", "Critical"].includes(c.latestIntegrityRiskLevel || "") || (c.latestIntegrityPenalty ?? 0) > 0
  )).length;
  const shortlistedCount = candidates.filter((c) => c.shortlisted || c.interviewStatus === "Shortlisted").length;
  const selectedJob = jobs.find((job) => job.jobId === selectedJobId);
  const shortlistThresholdCopy = selectedJob
    ? `Top ${openPositionsForJob(selectedJob)} for ${selectedJob.openPositions ?? 10} open position(s), pass ${selectedJob.minPassScore}/100`
    : "Top interview scores per job, based on each job's open positions";

  async function copyRecommendedShortlist() {
    if (!recommendedShortlist.length) {
      setMessage("No recommended candidates above threshold yet.");
      return;
    }
    const lines = [
      "Rank\tName\tEmail\tCollege\tDepartment\tGraduation Year\tJob\tScore\tThreshold\tSignal\tStatus",
      ...recommendedShortlist.map((item, index) => [
        index + 1,
        item.candidate.name,
        item.candidate.email,
        item.candidate.collegeName || "",
        item.candidate.department || "",
        item.candidate.graduationYear || "",
        item.job?.title || "Unknown job",
        item.displayScore,
        item.thresholdLabel,
        item.signal,
        item.candidate.interviewStatus,
      ].join("\t")),
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setMessage(`Copied ${recommendedShortlist.length} recommended candidate(s).`);
    } catch {
      setMessage("Copy failed. Select and copy the table manually.");
    }
  }

  function exportRecommendedShortlistCsv() {
    if (!recommendedShortlist.length) {
      setMessage("No recommended candidates above threshold yet.");
      return;
    }
    const headers = ["Rank", "Name", "Email ID", "College", "Department", "Graduation Year", "Job", "Score", "Threshold", "Signal", "Status"];
    const rows = recommendedShortlist.map((item, index) => [
      index + 1,
      item.candidate.name,
      item.candidate.email,
      item.candidate.collegeName || "",
      item.candidate.department || "",
      item.candidate.graduationYear || "",
      item.job?.title || "Unknown job",
      item.displayScore,
      item.thresholdLabel,
      item.signal,
      item.candidate.interviewStatus,
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const jobPart = selectedJob ? selectedJob.title : "all-jobs";
    link.href = url;
    link.download = `talentryx-final-shortlist-${safeFilenamePart(jobPart)}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMessage(`Downloaded ${recommendedShortlist.length} recommended candidate(s) as CSV.`);
  }

  return (
    <div>
      {/* ── Gradient Top Bar ── */}
      <div className="recruiter-topbar">
        <h2>Talentryx AI - Recruiter Intelligence Dashboard</h2>
        <p>AI-powered interview analysis platform</p>
      </div>

      <p className="recruiter-notice">
        AI scores and proctoring risk indicators are review aids. They may be affected by answer quality, audio clarity,
        resume context, browser behavior, network conditions, camera quality, lighting, accessibility needs, or model limitations.
      </p>

      {/* ── Navigation Tabs ── */}
      <div className="recruiter-nav">
        <button className={tab === "candidates" ? "active" : ""} onClick={() => setTab("candidates")}>
          <ClipboardList size={16} /> Candidates
        </button>
        <button className={tab === "jobs" ? "active" : ""} onClick={() => setTab("jobs")}>
          <BriefcaseBusiness size={16} /> Jobs
        </button>
        <button className={tab === "analytics" ? "active" : ""} onClick={() => setTab("analytics")}>
          <BarChart3 size={16} /> Analytics
        </button>
        <button className={tab === "billing" ? "active" : ""} onClick={() => setTab("billing")}>
          <CreditCard size={16} /> Billing
        </button>
      </div>

      {/* ════════ CANDIDATES TAB ════════ */}
      {tab === "candidates" && (
        <>
          {reportCandidate && reportResult ? (
            <CandidateFullReport
              candidate={reportCandidate}
              job={jobs.find((job) => job.jobId === reportCandidate.jobId) || selectedJob}
              result={reportResult}
              expandedQuestion={expandedQuestion}
              onToggleQuestion={(index) => setExpandedQuestion(expandedQuestion === index ? null : index)}
              onBack={() => {
                setReportCandidate(null);
                setReportResult(null);
              }}
            />
          ) : (
          <>
          {/* Invitation Status */}
          <h3 className="section-title">Invitation Status</h3>
          <div className="metric-row">
            <div className="metric-card"><span className="mc-label invited">INVITED</span><span className="mc-value">{invitedCount}</span></div>
            <div className="metric-card"><span className="mc-label started">STARTED</span><span className="mc-value">{startedCount}</span></div>
            <div className="metric-card"><span className="mc-label completed">COMPLETED</span><span className="mc-value">{completedCount}</span></div>
            <div className="metric-card"><span className="mc-label expired">EXPIRED</span><span className="mc-value">{expiredCount}</span></div>
          </div>

          {/* Summary metrics */}
          <div className="metric-row" style={{ marginTop: 16 }}>
            <div className="metric-card"><span className="mc-label">👥 TOTAL</span><span className="mc-value">{candidates.length}</span></div>
            <div className="metric-card"><span className="mc-label">📊 AVG SCORE</span><span className="mc-value">{avgScore === null ? "—" : avgScore}</span></div>
            <div className="metric-card"><span className="mc-label">✅ PASS RATE</span><span className="mc-value">{passRate === null ? "—" : `${passRate}%`}</span></div>
            <div className="metric-card"><span className="mc-label">🚩 FLAGGED</span><span className="mc-value">{flaggedCount}</span></div>
            <div className="metric-card"><span className="mc-label">⭐ SHORTLISTED</span><span className="mc-value">{shortlistedCount}</span></div>
          </div>

          <section className="top-shortlist">
            <div className="panel-title shortlist-title">
              <div>
                <h3><CheckCircle2 size={18} /> Final Interview Shortlist</h3>
                <p>Interview-score ranking only - {shortlistThresholdCopy}</p>
              </div>
              <div className="shortlist-actions">
                <button className="secondary-btn row-action" onClick={() => void copyRecommendedShortlist()}>
                  <ClipboardList size={15} /> Copy Table
                </button>
                <button className="secondary-btn row-action" onClick={exportRecommendedShortlistCsv}>
                  <Download size={15} /> CSV
                </button>
              </div>
            </div>
            {recommendedShortlist.length > 0 ? (
              <div className="shortlist-table-wrap">
                <table className="shortlist-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Name</th>
                      <th>Email ID</th>
                      <th>College</th>
                      <th>Job</th>
                      <th>Score</th>
                      <th>Signal</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendedShortlist.map((item, index) => (
                      <tr key={`${item.candidate.jobId}-${item.candidate.candidateId}`}>
                        <td>{index + 1}</td>
                        <td>{item.candidate.name}</td>
                        <td>{item.candidate.email}</td>
                        <td>
                          {item.candidate.collegeName || "Unassigned"}
                          {item.candidate.department || item.candidate.graduationYear ? (
                            <span>{[item.candidate.department, item.candidate.graduationYear].filter(Boolean).join(" - ")}</span>
                          ) : null}
                        </td>
                        <td>{item.job?.title || "Unknown job"}</td>
                        <td>{item.displayScore} <span>min {item.thresholdLabel}</span></td>
                        <td>{item.signal}</td>
                        <td>{item.candidate.interviewStatus}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="shortlist-empty">
                <Users size={24} />
                <p>No scored interviews are above the configured pass threshold yet.</p>
              </div>
            )}
          </section>

          {recentActivity.length > 0 && (
            <section className="recent-results">
              <div className="panel-title">
                <h3>Recent Interview Results</h3>
                <p>{selectedJobId ? selectedJob?.title : "All jobs"}</p>
              </div>
              <div className="recent-results-grid">
                {recentActivity.map((candidate) => (
                  <button
                    key={`${candidate.jobId}-${candidate.candidateId}`}
                    className="recent-result-card"
                    onClick={() => void openFullReport(candidate)}
                  >
                    <div>
                      <strong>{candidate.name}</strong>
                      <span>{candidateJobTitle(candidate)} - {formatShortDate(activityTime(candidate)) || "recent"}</span>
                    </div>
                    <span className={`score-dot ${scoreTone(candidate.latestResultScore ?? 0)}`} />
                    <strong>{typeof candidate.latestResultScore === "number" ? `${candidate.latestResultScore}/100` : candidate.interviewStatus}</strong>
                  </button>
                ))}
              </div>
            </section>
          )}

          {/* Search + Filter */}
          <div className="candidate-toolbar">
            <div className="search-box">
              <Search size={16} />
              <input placeholder="Search by name, email, or job..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
            </div>
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="All">All</option>
              <option value="Shortlisted">Shortlisted</option>
              <option value="Invited">Invited</option>
              <option value="In Progress">In Progress</option>
              <option value="Completed">Completed</option>
              <option value="Interview Submitted">Interview Submitted</option>
              <option value="Scored">Scored</option>
              <option value="Passed">Passed</option>
              <option value="Review Required">Review Required</option>
              <option value="Below Threshold">Below Threshold</option>
              <option value="Expired">Expired</option>
            </select>
            <select value={filterCollege} onChange={(e) => setFilterCollege(e.target.value)}>
              <option value="All">All colleges</option>
              {availableColleges.map((college) => <option key={college} value={college}>{college}</option>)}
              {candidates.some((candidate) => !candidate.collegeName) && <option value="Unassigned">Unassigned</option>}
            </select>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)}>
              <option value="date">Sort: Recent</option>
              <option value="name">Sort: Name</option>
              <option value="score">Sort: Score</option>
              <option value="status">Sort: Status</option>
            </select>
            <select value={selectedJobId} onChange={(e) => selectJob(e.target.value)}>
              <option value="">All jobs</option>
              {jobs.map((j) => <option key={j.jobId} value={j.jobId}>{jobOptionLabel(j)}</option>)}
            </select>
            <button className="icon-button" onClick={() => run("Refresh", async () => {
              const loadedJobs = await refreshJobs();
              await refreshCandidates(selectedJobId, loadedJobs);
            })}><RefreshCw size={16} /></button>
          </div>

          {/* Candidate List */}
          <div className="candidate-list">
            {filteredCandidates.length === 0 && (
              <div className="empty-state">
                <Users size={28} />
                <p>No candidates match the current filters.</p>
              </div>
            )}
            {filteredCandidates.map((c) => (
              <div
                key={`${c.jobId}-${c.candidateId}`}
                className={`candidate-row ${c.candidateId === selectedCandidateId ? "selected" : ""}`}
                onClick={() => { setSelectedCandidateId(c.candidateId); setResult(null); }}
              >
              <div className="cr-info">
                  <strong>{c.name}</strong>
                  <span>{c.email}{c.matchScore ? ` • Match: ${c.matchScore}/10` : ""}</span>
                  <span className="hint-text">{candidateSourceLabel(c) || "College source not set"}</span>
                  <span className="hint-text">Job: {candidateJobTitle(c)}</span>
                  {typeof c.latestResultScore === "number" && (
                    <span className="hint-text">
                      Score {c.latestResultScore}/100 • {c.latestRecommendation || c.latestAssessmentStatus || "Reviewed"}
                      {c.latestIntegrityRiskLevel ? ` • Risk ${c.latestIntegrityRiskLevel}` : ""}
                    </span>
                  )}
                </div>
                <div className="candidate-row-actions">
                  <span className={`status-badge ${c.interviewStatus.toLowerCase().replace(/\s+/g, "-")}`}>
                    {c.interviewStatus}
                  </span>
                  {canAllowRetest(c) && (
                    <button
                      className="secondary-btn row-action"
                      onClick={(event) => {
                        event.stopPropagation();
                        void run("Allow retest", () => allowRetestFor(c));
                      }}
                    >
                      <RefreshCw size={15} /> Retest
                    </button>
                  )}
                  <button
                    className="secondary-btn row-action"
                    onClick={(event) => {
                      event.stopPropagation();
                      void openFullReport(c);
                    }}
                  >
                    <Eye size={15} /> Full Report
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Selected Candidate Actions */}
          {selectedCandidateId && (
            <section className="panel" style={{ marginTop: 16 }}>
              <div className="panel-title">
                <h3>Interview Workflow</h3>
                <p>{busy || message || "Ready"}</p>
              </div>
              <div className="actions">
                <button disabled={!activeCandidateJobId} onClick={() => run("Prepare", async () => { await api.prepareInterview(activeCandidateJobId, selectedCandidateId); await refreshCandidates(selectedJobId); })}>
                  <Sparkles size={17} /> Prepare
                </button>
                <button onClick={() => run("Send invite", async () => {
                  if (!activeCandidateJobId) throw new Error("Select a candidate before sending an invite.");
                  await api.prepareInterview(activeCandidateJobId, selectedCandidateId);
                  const invite = await api.sendInvite(activeCandidateJobId, selectedCandidateId);
                  setLastInvite({
                    username: invite.username || "",
                    password: invite.password || "",
                    interviewUrl: invite.interviewUrl,
                  });
                  await refreshCandidates(selectedJobId);
                  await refreshBilling();
                })}>
                  <Mail size={17} /> Invite
                </button>
                <button disabled={!activeCandidateJobId} onClick={() => run("Score", async () => { await api.startScoring(activeCandidateJobId, selectedCandidateId); await refreshCandidates(selectedJobId); })}>
                  <Play size={17} /> Score
                </button>
                <button disabled={!activeCandidateJobId} onClick={() => run("Load result", async () => { const p = await api.getResult(activeCandidateJobId, selectedCandidateId); setResult(p.result as DetailedResult); })}>
                  <RefreshCw size={17} /> Result
                </button>
                {selectedCandidateCanRetest && selectedCandidate && (
                  <button onClick={() => run("Allow retest", () => allowRetestFor(selectedCandidate))}>
                    <RefreshCw size={17} /> Allow Retest
                  </button>
                )}
                <button onClick={() => {
                  const candidate = candidates.find((c) => c.candidateId === selectedCandidateId);
                  if (candidate) void openFullReport(candidate);
                }}>
                  <Eye size={17} /> Full Report
                </button>
                {result?.reportDownload && <a className="button-link" href={result.reportDownload.url}><Download size={17} /> PDF</a>}
                {result && <button onClick={() => setShowDetails(!showDetails)}><ChevronDown size={17} /> {showDetails ? "Hide" : "Details"}</button>}
              </div>

              {lastInvite && (
                <div className="login-status success" style={{ marginTop: 12 }}>
                  Candidate credentials ready: username <strong>{lastInvite.username}</strong>, password <strong>{lastInvite.password}</strong>.
                  Open Candidate Login and use these credentials.
                </div>
              )}

              {result && (
                <>
                  <div className="result">
                    <div><span className="metric">{result.finalScore}</span><p>Final score</p></div>
                    <div><span className="metric text">{result.assessmentStatus || "Reviewed"}</span><p>Assessment</p></div>
                    <div><span className="metric text">{result.recommendation}</span><p>Recommendation</p></div>
                    <div><span className="metric text">{result.integrityRisk.level}</span><p>Integrity risk</p></div>
                  </div>
                  {showDetails && result.integrityRisk && (
                    <div style={{ marginTop: 16 }}>
                      <h4 style={{ margin: "0 0 6px", fontSize: 14 }}>Proctoring Signals</h4>
                      <div className="integrity-detail">
                        <div><strong>{result.integrityRisk.tabSwitches}</strong>Tab switches</div>
                        <div><strong>{result.integrityRisk.fullscreenExits}</strong>Fullscreen exits</div>
                        <div><strong>{result.integrityRisk.copyPasteAttempts}</strong>Copy/paste</div>
                        <div><strong>{result.integrityRisk.devtoolsAttempts}</strong>DevTools</div>
                        <div><strong>{result.integrityRisk.faceNotDetected ?? 0}</strong>Face absent</div>
                        <div><strong>{result.integrityRisk.multipleFaces ?? 0}</strong>Multiple faces</div>
                      </div>
                    </div>
                  )}
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
                                {Object.entries(pq.dimensions).map(([k, v]) => (
                                  <div key={k} className="dimension-card">
                                    <span className="dim-score">{v as number}</span>
                                    <span className="dim-label">{k.replace(/([A-Z])/g, " $1").trim()}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {pq.keyStrength && pq.keyStrength !== "N/A" && <p><strong>Strength:</strong> {pq.keyStrength}</p>}
                            {pq.keyImprovement && pq.keyImprovement !== "N/A" && <p><strong>Improve:</strong> {pq.keyImprovement}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </section>
          )}
          </>
          )}
        </>
      )}

      {/* ════════ JOBS TAB ════════ */}
      {tab === "jobs" && (
        <>
          <h3 className="section-title"><BriefcaseBusiness size={20} /> Job Postings</h3>
          <div className="job-tabs">
            <button className={jobStep === "details" ? "active" : ""} onClick={() => setJobStep("details")}>+ New Job Posting</button>
            <button className={jobStep === "resumes" ? "active" : ""} onClick={() => setJobStep("resumes")}>📋 Active Postings</button>
          </div>

          {jobStep === "details" && (
            <section className="panel" style={{ marginTop: 16 }}>
              <h3>Step 1 — Job Details</h3>
              <div className="job-form-grid">
                <label className="job-field">
                  <span>Job Title *</span>
                  <input placeholder="e.g. Python Backend Developer" value={jobForm.title}
                    onChange={(e) => setJobForm({ ...jobForm, title: e.target.value })} />
                </label>
                <label className="job-field">
                  <span>Min Pass Score (out of 100)</span>
                  <input type="number" min={0} max={100} value={jobForm.minPassScore}
                    onChange={(e) => setJobForm({ ...jobForm, minPassScore: Number(e.target.value) })} />
                </label>
                <label className="job-field">
                  <span>Open Positions</span>
                  <input type="number" min={1} max={20} value={jobForm.openPositions}
                    onChange={(e) => setJobForm({ ...jobForm, openPositions: Number(e.target.value) })} />
                </label>
                <label className="job-field">
                  <span>Shortlist Threshold (/10)</span>
                  <input type="number" min={0} max={10} step={0.5} value={jobForm.shortlistThreshold}
                    onChange={(e) => setJobForm({ ...jobForm, shortlistThreshold: Number(e.target.value) })} />
                </label>
                <label className="job-field wide">
                  <span>Job Description *</span>
                  <textarea placeholder="Paste the full job description here..." value={jobForm.jdText}
                    onChange={(e) => setJobForm({ ...jobForm, jdText: e.target.value })} />
                </label>
                <label className="job-field">
                  <span>Interview Deadline</span>
                  <input type="date" value={jobForm.deadline}
                    onChange={(e) => setJobForm({ ...jobForm, deadline: e.target.value })} />
                </label>
              </div>

              <h3 style={{ marginTop: 24 }}>Step 2 — Upload Resumes</h3>
              <p style={{ fontSize: 13, color: "#697780" }}>Upload resume PDFs (multiple allowed)</p>
              <div className="job-form-grid compact-source">
                <label className="job-field">
                  <span>College Name</span>
                  <input placeholder="e.g. ABC Engineering College" value={candidateSource.collegeName}
                    onChange={(e) => setCandidateSource({ ...candidateSource, collegeName: e.target.value })} />
                </label>
                <label className="job-field">
                  <span>Department</span>
                  <input placeholder="e.g. CSE" value={candidateSource.department}
                    onChange={(e) => setCandidateSource({ ...candidateSource, department: e.target.value })} />
                </label>
                <label className="job-field">
                  <span>Graduation Year</span>
                  <input placeholder="e.g. 2026" value={candidateSource.graduationYear}
                    onChange={(e) => setCandidateSource({ ...candidateSource, graduationYear: e.target.value })} />
                </label>
              </div>
              <label className="file-input" style={{ marginBottom: 12 }}>
                <Upload size={18} />
                <input type="file" accept="application/pdf" multiple
                  onChange={(e) => setResumeFiles(Array.from(e.target.files || []))} />
                {resumeFiles.length > 0 ? `${resumeFiles.length} file(s) selected` : "Drag and drop files here • Browse files"}
              </label>

              <button className="analyse-btn" disabled={!jobForm.title || !jobForm.jdText || !!busy}
                onClick={() => run("Analyse resumes", async () => {
                  if (isDemo) {
                    setMessage("Demo mode — job creation simulated.");
                    return;
                  }
                  // Step 1: Create the job and get back the real jobId
                  const jobResult = await api.createJob(jobForm);
                  const newJobId = jobResult.job.jobId;
                  setSelectedJobId(newJobId);
                  setShortlistJobId(newJobId);
                  await refreshJobs();

                  // Step 2: Upload each resume as a candidate
                  for (const file of resumeFiles) {
                    const candidateName = file.name.replace(/\.pdf$/i, "").replace(/[_-]/g, " ");
                    const created = await api.createCandidate(newJobId, {
                      name: candidateName,
                      email: `${candidateName.toLowerCase().replace(/\s+/g, ".")}@pending.local`,
                      resumeFilename: file.name,
                      collegeName: candidateSource.collegeName.trim(),
                      department: candidateSource.department.trim(),
                      graduationYear: candidateSource.graduationYear.trim(),
                    });
                    await api.uploadResume(created.resumeUpload, file);
                  }

                  // Step 3: Analyse all resumes against JD
                  const analysis = await api.analyseResumes(newJobId);
                  setMatchResults(analysis.results.map((r) => ({
                    ...r,
                    rowId: r.candidateId || r.name,
                    filename: r.name,
                    resumeText: r.resumeText ?? "",
                    collegeName: r.collegeName || candidateSource.collegeName.trim(),
                    department: r.department || candidateSource.department.trim(),
                    graduationYear: r.graduationYear || candidateSource.graduationYear.trim(),
                    selected: r.shortlisted ?? ((r.matchScore ?? 0) >= (jobForm.shortlistThreshold || 7)),
                  })));
                  setJobStep("shortlist");

                  // Step 4: Refresh candidates with updated match data
                  await refreshCandidates(newJobId);
                })}>
                <Sparkles size={17} /> Analyse Resumes
              </button>
              {message && <p className="form-message">{message}</p>}
            </section>
          )}

          {jobStep === "resumes" && (
            <section className="panel" style={{ marginTop: 16 }}>
              <div className="panel-title">
                <h3>Active Postings</h3>
                <button className="icon-button" onClick={() => run("Refresh", async () => { await refreshJobs(); })}><RefreshCw size={16} /></button>
              </div>
              {jobs.length === 0 && (
                <div className="empty-state">
                  <FileText size={28} />
                  <p>No job postings yet. Create one using "New Job Posting".</p>
                </div>
              )}
              <div className="list">
                {jobs.map((j) => (
                  <div key={j.jobId} className={`candidate-row ${j.jobId === selectedJobId ? "selected" : ""}`}
                    onClick={() => selectJob(j.jobId)}>
                    <div className="cr-info">
                      <strong>{j.title}</strong>
                      <span>Open positions: {j.openPositions ?? 10} - Pass: {j.minPassScore}/100 - {j.status}</span>
                    </div>
                    <span className="status-badge completed">{j.status}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Shortlist Review */}
          {jobStep === "shortlist" && matchResults.length > 0 && (
            <section className="panel" style={{ marginTop: 16 }}>
              <h3>Step 3 — Review Shortlist</h3>
              <p style={{ fontSize: 13, color: "#697780" }}>Uncheck candidates you want to exclude before sending invites.</p>
              <div className="candidate-list">
                {matchResults.map((r) => (
                  <div key={r.rowId} className={`candidate-row ${r.selected ? "selected" : ""}`}
                    onClick={() => setMatchResults(matchResults.map((m) => m.rowId === r.rowId ? { ...m, selected: !m.selected } : m))}>
                    <div className="cr-info">
                      <strong>{r.selected ? "☑" : "☐"} {r.name || "Unknown"}</strong>
                      <span>{r.email || "No email"} • {r.filename} • Score: {r.matchScore}/10</span>
                      <span style={{ fontSize: 11, color: "#697780" }}>{r.matchReason}</span>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
                        <input
                          value={r.name}
                          placeholder="Candidate name"
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setMatchResults(matchResults.map((m) => (
                            m.rowId === r.rowId ? { ...m, name: event.target.value } : m
                          )))}
                        />
                        <input
                          value={r.email}
                          placeholder="candidate@email.com"
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setMatchResults(matchResults.map((m) => (
                            m.rowId === r.rowId ? { ...m, email: event.target.value } : m
                          )))}
                        />
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr 0.8fr", gap: 8, marginTop: 8 }}>
                        <input
                          value={r.collegeName || ""}
                          placeholder="College name"
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setMatchResults(matchResults.map((m) => (
                            m.rowId === r.rowId ? { ...m, collegeName: event.target.value } : m
                          )))}
                        />
                        <input
                          value={r.department || ""}
                          placeholder="Department"
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setMatchResults(matchResults.map((m) => (
                            m.rowId === r.rowId ? { ...m, department: event.target.value } : m
                          )))}
                        />
                        <input
                          value={r.graduationYear || ""}
                          placeholder="Grad year"
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setMatchResults(matchResults.map((m) => (
                            m.rowId === r.rowId ? { ...m, graduationYear: event.target.value } : m
                          )))}
                        />
                      </div>
                    </div>
                    <span className={`status-badge ${r.matchScore >= 7 ? "completed" : r.matchScore >= 5 ? "in-progress" : "expired"}`}>
                      {r.matchScore}/10
                    </span>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 13, fontWeight: 600, marginTop: 12 }}>
                {matchResults.filter((r) => r.selected).length} candidate(s) selected for invite
              </p>
              <button className="analyse-btn" disabled={matchResults.filter((r) => r.selected).length === 0}
                onClick={() => run("Send invites", async () => {
                  if (isDemo) {
                    const selectedForDemo = matchResults.filter((r) => r.selected);
                    const simulated = selectedForDemo.map((r, index) => ({
                      candidateId: r.rowId,
                      name: r.name || "Demo Candidate",
                      email: r.email || `candidate-${index + 1}@talentryx.demo`,
                      username: r.email || `candidate-${index + 1}@talentryx.demo`,
                      password: `TX-DEMO${index + 1}`,
                      interviewUrl: `${window.location.origin}/?mode=candidate&orgId=demo-org&jobId=${encodeURIComponent(shortlistJobId || selectedJobId || "demo-job")}&candidateId=${encodeURIComponent(r.rowId)}`,
                      provider: "demo",
                    }));
                    setBulkInvites(simulated);
                    return `Demo mode - ${simulated.length} invite credential(s) simulated.`;
                  }
                  if (isDemo) { setMessage(`Demo mode — ${matchResults.filter((r) => r.selected).length} invite(s) simulated.`); return; }
                  const selected = matchResults.filter((r) => r.selected);
                  setBulkInvites([]);
                  const jobIdForInvite = shortlistJobId || selectedJobId;
                  for (const r of matchResults) {
                    await api.updateCandidate(jobIdForInvite, r.rowId, {
                      name: r.name,
                      email: r.email,
                      collegeName: r.collegeName || "",
                      department: r.department || "",
                      graduationYear: r.graduationYear || "",
                      shortlisted: r.selected,
                    });
                  }
                  const sentInvites: typeof bulkInvites = [];
                  for (const s of selected) {
                    try {
                      await api.prepareInterview(jobIdForInvite, s.rowId);
                      const invite = await api.sendInvite(jobIdForInvite, s.rowId);
                      sentInvites.push({
                        candidateId: s.rowId,
                        name: s.name || invite.username || "Candidate",
                        email: s.email || invite.username || "",
                        username: invite.username || s.email || "",
                        password: invite.password || "",
                        interviewUrl: invite.interviewUrl,
                        provider: invite.provider,
                      });
                    } catch (error) {
                      setBulkInvites(sentInvites);
                      await refreshCandidates(jobIdForInvite);
                      await refreshBilling();
                      const reason = error instanceof Error ? error.message : String(error);
                      throw new Error(
                        sentInvites.length
                          ? `${sentInvites.length} invite(s) sent before stopping: ${reason}`
                          : reason,
                      );
                    }
                  }
                  setBulkInvites(sentInvites);
                  await refreshCandidates(jobIdForInvite);
                  await refreshBilling();
                  const localOnly = sentInvites.some((invite) => invite.provider === "local");
                  return localOnly
                    ? `${sentInvites.length} invite credential(s) generated locally. n8n is not configured in serverless/.env, so no real email was sent.`
                    : `${sentInvites.length} invite(s) sent through the configured invite provider.`;
                })}>
                <Mail size={17} /> Send Invites to {matchResults.filter((r) => r.selected).length} Candidate(s)
              </button>
              {message && <p className="form-message">{message}</p>}
              {bulkInvites.length > 0 && (
                <div className="bulk-invite-results">
                  <strong>Candidate login credentials</strong>
                  {bulkInvites.map((invite) => (
                    <div className="bulk-invite-row" key={invite.candidateId}>
                      <div>
                        <strong>{invite.name}</strong>
                        <span>{invite.email}</span>
                      </div>
                      <div>
                        <span>Username</span>
                        <code>{invite.username}</code>
                      </div>
                      <div>
                        <span>Password</span>
                        <code>{invite.password}</code>
                      </div>
                      <a href={invite.interviewUrl} target="_blank" rel="noreferrer">Open interview</a>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}

      {/* ════════ ANALYTICS TAB ════════ */}
      {tab === "analytics" && (
        <section className="panel">
          <h3>📈 Analytics</h3>
          <div className="metric-row">
            <div className="metric-card"><span className="mc-label">TOTAL INTERVIEWS</span><span className="mc-value">{candidates.length}</span></div>
            <div className="metric-card"><span className="mc-label">COMPLETED</span><span className="mc-value">{completedCount}</span></div>
            <div className="metric-card"><span className="mc-label">ACTIVE JOBS</span><span className="mc-value">{jobs.length}</span></div>
            <div className="metric-card"><span className="mc-label">PASS RATE</span><span className="mc-value">{candidates.length > 0 ? `${Math.round(completedCount / candidates.length * 100)}%` : "—"}</span></div>
          </div>
          <div className="empty-state" style={{ marginTop: 20 }}>
            <BarChart3 size={28} />
            <p>Detailed analytics charts will be available when connected to the live API.</p>
          </div>
        </section>
      )}

      {tab === "billing" && (
        <BillingPanel
          billing={billing}
          loading={billingLoading}
          error={billingError}
          onRefresh={() => void refreshBilling()}
        />
      )}
    </div>
  );
}
