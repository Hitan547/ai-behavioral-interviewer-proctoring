import { ArrowLeft, FileCheck2, LockKeyhole, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

export type LegalPageName = "privacy" | "terms" | "proctoring";

type LegalPageProps = {
  page: LegalPageName;
  backHref?: string;
};

export function isLegalPage(value: string | null): value is LegalPageName {
  return value === "privacy" || value === "terms" || value === "proctoring";
}

const pageMeta: Record<LegalPageName, { title: string; subtitle: string; icon: ReactNode }> = {
  privacy: {
    title: "Privacy Notice",
    subtitle: "How Talentryx AI handles recruiter, candidate, resume, interview, and proctoring data.",
    icon: <LockKeyhole size={22} />,
  },
  terms: {
    title: "Terms of Use",
    subtitle: "Rules for using Talentryx AI as an AI-assisted interview and proctoring platform.",
    icon: <FileCheck2 size={22} />,
  },
  proctoring: {
    title: "Proctoring Notice",
    subtitle: "What integrity signals are collected and how recruiters should review them.",
    icon: <ShieldCheck size={22} />,
  },
};

export function LegalPage({ page, backHref = "/" }: LegalPageProps) {
  const meta = pageMeta[page];

  return (
    <main className="legal-shell">
      <section className="legal-card">
        <div className="legal-header">
          <a className="legal-back" href={backHref}>
            <ArrowLeft size={16} /> Back
          </a>
          <div className="legal-brand">
            <div className="brand-mark">TX</div>
            <div>
              <strong>Talentryx AI</strong>
              <span>AI behavioral interview platform</span>
            </div>
          </div>
        </div>

        <div className="legal-title">
          <span>{meta.icon}</span>
          <div>
            <h1>{meta.title}</h1>
            <p>{meta.subtitle}</p>
          </div>
        </div>

        <nav className="legal-tabs" aria-label="Legal pages">
          <a className={page === "privacy" ? "active" : ""} href="?page=privacy">Privacy</a>
          <a className={page === "terms" ? "active" : ""} href="?page=terms">Terms</a>
          <a className={page === "proctoring" ? "active" : ""} href="?page=proctoring">Proctoring</a>
        </nav>

        {page === "privacy" && <PrivacyContent />}
        {page === "terms" && <TermsContent />}
        {page === "proctoring" && <ProctoringContent />}

        <div className="legal-footnote">
          These notices are product-ready starter text for review. Before paid production launch, have your legal owner approve the final wording.
        </div>
      </section>
    </main>
  );
}

function PrivacyContent() {
  return (
    <div className="legal-content">
      <h2>Data We Collect</h2>
      <p>
        Talentryx AI stores recruiter account details, organization details, job descriptions, candidate names,
        candidate email addresses, resume files, resume analysis output, interview answers, transcripts,
        scoring outputs, reports, billing usage, and integrity signals.
      </p>

      <h2>Interview And Proctoring Data</h2>
      <p>
        During an interview, Talentryx AI may process microphone audio for transcription and collect browser
        integrity signals such as tab changes, fullscreen exits, copy/paste attempts, developer tool attempts,
        face visibility counts, and multiple-face counts. The current serverless flow stores these as review
        signals, not as final hiring decisions.
      </p>

      <h2>How Data Is Used</h2>
      <p>
        Data is used to prepare interview questions from the job description and resume context, generate
        candidate reports, show recruiter dashboards, support billing limits, and maintain an audit trail for
        interview invitations, submissions, scoring, and retest actions.
      </p>

      <h2>Infrastructure</h2>
      <p>
        The AWS serverless deployment is designed around Cognito, API Gateway, Lambda, DynamoDB, S3, SSM
        Parameter Store, Step Functions, and CloudWatch. Candidate invite emails are sent through the configured
        n8n webhook provider.
      </p>

      <h2>Retention And Access</h2>
      <p>
        Recruiters should keep candidate data only as long as needed for the hiring process. Candidates can ask
        the recruiter or organization owner to review, correct, or delete their information according to the
        recruiter's hiring policy and applicable law.
      </p>
    </div>
  );
}

function TermsContent() {
  return (
    <div className="legal-content">
      <h2>Recruiter Responsibility</h2>
      <p>
        Talentryx AI is a decision-support tool. Recruiters must review candidate answers, job requirements,
        accessibility needs, technical issues, and business context before making hiring decisions.
      </p>

      <h2>Candidate Consent</h2>
      <p>
        Candidates must see the AI-assisted interview notice and accept the consent checkbox before starting
        the interview. Candidates should not continue if they do not agree to transcription, scoring, and
        integrity signal collection.
      </p>

      <h2>Acceptable Use</h2>
      <p>
        Users must not upload unlawful content, attempt to bypass interview controls, impersonate candidates,
        misuse credentials, or use Talentryx AI as the sole basis for employment decisions.
      </p>

      <h2>AI Output Limits</h2>
      <p>
        Scores, summaries, recommendations, and proctoring risk labels can be affected by audio quality, resume
        context, browser behavior, camera quality, network conditions, accessibility needs, and model limitations.
      </p>

      <h2>Service Operation</h2>
      <p>
        The product may change as features improve. Billing limits, trial access, data retention, integrations,
        and organization policies should be confirmed in the active plan before production use.
      </p>
    </div>
  );
}

function ProctoringContent() {
  return (
    <div className="legal-content">
      <h2>What Is Collected</h2>
      <p>
        Talentryx AI records integrity counts for tab or window changes, fullscreen exits, copy and paste attempts,
        developer tool attempts, face-not-detected events, and multiple-face events. These events are shown to
        recruiters as risk indicators.
      </p>

      <h2>Fullscreen Behavior</h2>
      <p>
        The interview asks candidates to stay in fullscreen mode. If fullscreen is exited, the candidate is
        prompted to return. Candidates can leave the interview by signing out, but unfinished work may be marked
        incomplete.
      </p>

      <h2>Camera And Audio</h2>
      <p>
        The browser camera is used for the live interview check and face visibility signals. Microphone audio may
        be uploaded for transcription and scoring. The product stores proctoring counts and interview artifacts
        needed for recruiter review.
      </p>

      <h2>Human Review Required</h2>
      <p>
        Proctoring signals can have false positives. Lighting, camera angle, accessibility tools, browser
        permissions, assistive technology, or network interruptions can affect the result. Recruiters should
        review the transcript, candidate context, and any reported technical issue before deciding.
      </p>

      <h2>Retest Policy</h2>
      <p>
        A recruiter can allow a retest when a candidate has a valid reason or a technical issue. Retests are
        logged in the audit trail and issue fresh candidate credentials while keeping previous submissions stored
        for review.
      </p>
    </div>
  );
}
