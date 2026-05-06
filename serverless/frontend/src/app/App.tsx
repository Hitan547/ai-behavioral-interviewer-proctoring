import { BriefcaseBusiness, ClipboardCheck, FileText, UserRoundCheck } from "lucide-react";
import { CandidateInterview } from "../candidate/CandidateInterview";
import { RecruiterDashboard } from "../recruiter/RecruiterDashboard";
import { AuthPanel } from "../auth/AuthPanel";
import { useAuthSession } from "../auth/useAuthSession";

type AppMode = "recruiter" | "candidate";

export function App() {
  const auth = useAuthSession();
  const params = new URLSearchParams(window.location.search);
  const initialMode = params.get("candidateId") ? "candidate" : "recruiter";
  const mode = (params.get("mode") as AppMode | null) ?? initialMode;

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">P</div>
          <div>
            <h1>PsySense</h1>
            <p>Serverless MVP</p>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary">
          <a className={mode === "recruiter" ? "active" : ""} href="?mode=recruiter">
            <BriefcaseBusiness size={18} />
            Recruiter
          </a>
          <a className={mode === "candidate" ? "active" : ""} href="?mode=candidate">
            <UserRoundCheck size={18} />
            Candidate
          </a>
        </nav>

        <div className="sidebar-note">
          <ClipboardCheck size={18} />
          <span>Typed answers first. Camera and audio come later as separate serverless slices.</span>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">AWS Serverless Frontend</p>
            <h2>{mode === "candidate" ? "Candidate Interview" : "Recruiter Dashboard"}</h2>
          </div>
          <a className="doc-link" href="/README.md">
            <FileText size={17} />
            Docs
          </a>
        </header>

        <AuthPanel auth={auth} />

        {mode === "candidate" ? (
          <CandidateInterview auth={auth} />
        ) : (
          <RecruiterDashboard auth={auth} />
        )}
      </section>
    </main>
  );
}
