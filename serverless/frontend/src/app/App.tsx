import { BriefcaseBusiness, ClipboardCheck, LogOut, UserRoundCheck } from "lucide-react";
import { CandidateInterview } from "../candidate/CandidateInterview";
import { RecruiterDashboard } from "../recruiter/RecruiterDashboard";
import { LoginPage } from "../auth/AuthPanel";
import { useAuthSession } from "../auth/useAuthSession";
import { isLegalPage, LegalPage } from "../legal/LegalPages";

type AppMode = "recruiter" | "candidate";

export function App() {
  const auth = useAuthSession();
  const params = new URLSearchParams(window.location.search);
  const initialMode = params.get("candidateId") || auth.role === "candidate" ? "candidate" : "recruiter";
  const mode = (params.get("mode") as AppMode | null) ?? initialMode;
  const effectiveMode: AppMode = auth.role === "candidate" ? "candidate" : mode;
  const legalPage = params.get("page");

  const signedIn = auth.isSignedIn();

  if (isLegalPage(legalPage)) {
    const backHref = signedIn
      ? `?mode=${effectiveMode}${auth.candidateJobId && auth.candidateId ? `&orgId=${encodeURIComponent(auth.orgId)}&jobId=${encodeURIComponent(auth.candidateJobId)}&candidateId=${encodeURIComponent(auth.candidateId)}` : ""}`
      : "/";
    return <LegalPage page={legalPage} backHref={backHref} />;
  }

  // If not signed in, show full-page login (no sidebar, no dashboard)
  if (!signedIn) {
    return <LoginPage auth={auth} />;
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">TX</div>
          <div>
            <h1>Talentryx AI</h1>
            <p>AI Interview Platform</p>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary">
          {auth.role !== "candidate" && (
            <a className={effectiveMode === "recruiter" ? "active" : ""} href="?mode=recruiter">
              <BriefcaseBusiness size={18} />
              Recruiter
            </a>
          )}
          <a className={effectiveMode === "candidate" ? "active" : ""} href={`?mode=candidate${auth.candidateJobId && auth.candidateId ? `&orgId=${auth.orgId}&jobId=${auth.candidateJobId}&candidateId=${auth.candidateId}` : ""}`}>
            <UserRoundCheck size={18} />
            Candidate
          </a>
        </nav>

        {/* User profile section */}
        <div className="sidebar-user">
          <div className="sidebar-user-info">
            <div className="sidebar-user-avatar">{(auth.username || "U")[0].toUpperCase()}</div>
            <div>
              <div className="sidebar-user-name">{auth.username || "User"}</div>
              <div className="sidebar-user-role">
                {auth.isDemoMode ? "Demo Mode" : auth.role || "recruiter"}
                {auth.orgId && !auth.isDemoMode ? ` • ${auth.orgId}` : ""}
              </div>
            </div>
          </div>
          <button className="sidebar-logout" onClick={auth.clearSession}>
            <LogOut size={16} />
            Sign out
          </button>
          <div className="sidebar-legal-links">
            <a href="?page=privacy">Privacy</a>
            <a href="?page=terms">Terms</a>
            <a href="?page=proctoring">Proctoring</a>
          </div>
        </div>

        {auth.isDemoMode && (
          <div className="sidebar-note demo-badge">
            <ClipboardCheck size={18} />
            <span>Demo Mode — exploring with sample data. Connect to AWS to use live data.</span>
          </div>
        )}
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Talentryx AI Platform</p>
            <h2>{effectiveMode === "candidate" ? "Candidate Interview" : "Recruiter Dashboard"}</h2>
          </div>
        </header>

        {effectiveMode === "candidate" ? (
          <CandidateInterview auth={auth} />
        ) : (
          <RecruiterDashboard auth={auth} />
        )}
      </section>
    </main>
  );
}
