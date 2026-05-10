import { ChevronDown, ChevronUp, Eye, EyeOff, KeyRound, Play, Server, Settings } from "lucide-react";
import { useState } from "react";
import { ApiClient } from "../api/client";
import { claimsValue, signInWithCognito } from "./cognito";
import type { AuthSession } from "./useAuthSession";

type Props = {
  auth: AuthSession;
};

type AuthTab = "recruiter" | "signup" | "candidate";

export function LoginPage({ auth }: Props) {
  const [tab, setTab] = useState<AuthTab>("recruiter");
  const [email, setEmail] = useState(auth.username);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState("");
  const [statusType, setStatusType] = useState<"error" | "success">("error");
  const [showSettings, setShowSettings] = useState(false);

  // Signup fields
  const [orgName, setOrgName] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  function apiBaseForLocalDemo() {
    const value = auth.apiBaseUrl || "http://localhost:3001";
    auth.setApiBaseUrl(value);
    return value;
  }

  function isLocalApi(url = auth.apiBaseUrl || "http://localhost:3001") {
    return /localhost|127\.0\.0\.1/.test(url);
  }

  function applyRecruiterSession(result: {
    accessToken: string;
    idToken: string;
    orgId: string;
    role: "recruiter";
    username: string;
  }) {
    auth.setAccessToken(result.accessToken);
    auth.setIdToken(result.idToken);
    auth.setUsername(result.username);
    auth.setOrgId(result.orgId);
    auth.setRole("recruiter");
  }

  async function signIn() {
    setStatus("");
    try {
      if (tab === "candidate") {
        await signInCandidate();
        return;
      }
      const apiBaseUrl = apiBaseForLocalDemo();
      if (isLocalApi(apiBaseUrl) && (!auth.userPoolId || !auth.clientId)) {
        const api = new ApiClient({ ...auth, apiBaseUrl });
        const result = await api.recruiterLogin({ email, password });
        applyRecruiterSession(result);
        setPassword("");
        setStatusType("success");
        setStatus("Recruiter signed in to local demo.");
        return;
      }
      if (!auth.userPoolId || !auth.clientId) {
        throw new Error("Open Settings below and enter your Cognito User Pool ID and Client ID.");
      }
      const result = await signInWithCognito(
        { userPoolId: auth.userPoolId, clientId: auth.clientId },
        email,
        password,
      );
      auth.setAccessToken(result.accessToken);
      auth.setIdToken(result.idToken);
      auth.setUsername(email);
      auth.setOrgId(claimsValue(result.claims, ["custom:org_id", "org_id", "orgId"], auth.orgId));
      auth.setRole(claimsValue(result.claims, ["custom:role", "role"], auth.role));
      setPassword("");
      setStatusType("success");
      setStatus("Signed in successfully!");
    } catch (error) {
      setStatusType("error");
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function signUpRecruiter() {
    setStatus("");
    setStatusType("error");
    try {
      if (!orgName.trim()) throw new Error("Company/team name is required.");
      if (!email.trim()) throw new Error("Work email is required.");
      if (password !== confirmPassword) throw new Error("Passwords do not match.");
      const apiBaseUrl = apiBaseForLocalDemo();
      if (!isLocalApi(apiBaseUrl)) {
        if (!auth.userPoolId || !auth.clientId) {
          throw new Error("Open Settings below and enter your Cognito User Pool ID and Client ID.");
        }
        const api = new ApiClient({ ...auth, apiBaseUrl });
        const created = await api.recruiterSignup({ email, password, orgName });
        const result = await signInWithCognito(
          { userPoolId: auth.userPoolId, clientId: auth.clientId },
          email,
          password,
        );
        auth.setAccessToken(result.accessToken);
        auth.setIdToken(result.idToken);
        auth.setUsername(email);
        auth.setOrgId(claimsValue(result.claims, ["custom:org_id", "org_id", "orgId"], created.orgId));
        auth.setRole(claimsValue(result.claims, ["custom:role", "role"], "recruiter"));
        setPassword("");
        setConfirmPassword("");
        setStatusType("success");
        setStatus("Recruiter account created and signed in.");
        return;
      }
      const api = new ApiClient({ ...auth, apiBaseUrl });
      const result = await api.recruiterSignup({ email, password, orgName });
      applyRecruiterSession(result);
      setPassword("");
      setConfirmPassword("");
      setStatusType("success");
      setStatus("Recruiter account created and signed in to local demo.");
    } catch (error) {
      setStatusType("error");
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function signInCandidate() {
    const params = new URLSearchParams(window.location.search);
    const apiBaseUrl = auth.apiBaseUrl || "http://localhost:3001";
    auth.setApiBaseUrl(apiBaseUrl);
    const api = new ApiClient({ ...auth, apiBaseUrl });
    const result = await api.candidateLogin({
      username: email,
      password,
      orgId: params.get("orgId") || auth.orgId || "",
      jobId: params.get("jobId") || auth.candidateJobId || "",
      candidateId: params.get("candidateId") || auth.candidateId || "",
    });
    auth.setAccessToken(result.accessToken);
    auth.setIdToken(result.idToken);
    auth.setUsername(result.username);
    auth.setOrgId(result.orgId);
    auth.setRole("candidate");
    auth.setCandidateJobId(result.jobId);
    auth.setCandidateId(result.candidateId);
    setPassword("");
    setStatusType("success");
    setStatus("Candidate signed in successfully!");
    window.location.href = `?mode=candidate&orgId=${encodeURIComponent(result.orgId)}&jobId=${encodeURIComponent(result.jobId)}&candidateId=${encodeURIComponent(result.candidateId)}`;
  }

  function handleDemoMode() {
    auth.enterDemoMode();
  }

  function handleLocalDev() {
    // Set API to local server, fake token, real org — NOT demo mode
    auth.setApiBaseUrl("http://localhost:3001");
    auth.setAccessToken("local-dev-token");
    auth.setIdToken("local-dev-token");
    auth.setUsername("recruiter@talentryx.local");
    auth.setOrgId("local-org");
    auth.setRole("recruiter");
    setStatusType("success");
    setStatus("Connected to local dev server!");
  }

  function handleForgotPassword() {
    const apiBaseUrl = auth.apiBaseUrl || "http://localhost:3001";
    setStatusType("success");
    if (tab === "candidate") {
      setStatus("Candidate passwords are invite credentials. Ask the recruiter to resend an invite or allow a retest.");
      return;
    }
    if (isLocalApi(apiBaseUrl)) {
      setStatus("Local dev does not send password reset email. Use your test password or create a new local recruiter account.");
      return;
    }
    setStatus("AWS password reset is handled by Cognito. Use the configured Cognito reset flow after deployment.");
  }

  return (
    <div className="login-page">
      <div className="login-card">
        {/* Logo */}
        <div className="login-logo">
          <div className="login-logo-mark">TX</div>
          <h1 className="login-brand">Talentryx AI</h1>
          <p className="login-tagline">AI-powered interview screening and proctoring platform</p>
        </div>

        {/* Tab switcher */}
        <div className="login-tabs">
          <button className={tab === "recruiter" ? "active" : ""} onClick={() => setTab("recruiter")}>
            Recruiter Login
          </button>
          <button className={tab === "signup" ? "active" : ""} onClick={() => setTab("signup")}>
            Recruiter Signup
          </button>
          <button className={tab === "candidate" ? "active" : ""} onClick={() => setTab("candidate")}>
            Candidate Login
          </button>
        </div>

        {/* Login form */}
        {(tab === "recruiter" || tab === "candidate") && (
          <div className="login-form">
            <label>
              <span>{tab === "recruiter" ? "Username" : "Candidate email"}</span>
              <input
                value={email}
                placeholder={tab === "recruiter" ? "your_username" : "candidate@example.com"}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && signIn()}
              />
            </label>
            <label>
              <span>Password</span>
              <div className="password-field">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  placeholder="••••••••"
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && signIn()}
                />
                <button type="button" className="password-toggle" onClick={() => setShowPassword(!showPassword)}>
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>
            <button className="login-submit" onClick={signIn}>
              <KeyRound size={17} />
              {tab === "candidate" ? "Open Interview" : "Sign In"} →
            </button>
            <button className="login-forgot" onClick={handleForgotPassword}>
              Forgot Password?
            </button>
          </div>
        )}

        {/* Signup form */}
        {tab === "signup" && (
          <div className="login-form">
            <div className="signup-trial-banner">
              ✨ <strong>14-day free trial</strong> — no credit card required. Upgrade anytime.
            </div>
            <label>
              <span>Company/Team Name</span>
              <input value={orgName} placeholder="e.g., Acme Corp" onChange={(e) => setOrgName(e.target.value)} />
            </label>
            <label>
              <span>Work Email</span>
              <input value={email} placeholder="you@company.com" onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                value={password}
                placeholder="min 8 chars, must include a number"
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              <span>Confirm Password</span>
              <input
                type="password"
                value={confirmPassword}
                placeholder="repeat password"
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </label>
            <button
              className="login-submit"
              onClick={signUpRecruiter}
            >
              Create Account & Start Free Trial →
            </button>
            <p className="auth-helper-text">
              AWS deployment uses Cognito email identity and account recovery. Local dev signs in immediately for testing.
            </p>
          </div>
        )}

        {/* Status message */}
        {status && (
          <div className={`login-status ${statusType}`}>
            {status}
          </div>
        )}

        {/* Local dev mode */}
        <div className="login-demo-section">
          <div className="login-divider">
            <span>local development</span>
          </div>
          <button className="login-demo-btn" onClick={handleLocalDev} style={{ background: "linear-gradient(135deg, #2563eb, #1d4ed8)" }}>
            <Server size={17} />
            Local Dev Login
          </button>
          <p className="login-demo-hint">Recruiter access to local_server.py (localhost:3001) — no Cognito needed.</p>
        </div>

        {/* Demo mode */}
        <div className="login-demo-section">
          <div className="login-divider">
            <span>or</span>
          </div>
          <button className="login-demo-btn" onClick={handleDemoMode}>
            <Play size={17} />
            Explore Demo Dashboard
          </button>
          <p className="login-demo-hint">No account needed — explore the full recruiter & candidate UI with sample data.</p>
        </div>

        {/* Settings toggle */}
        <div className="login-settings-section">
          <button className="login-settings-toggle" onClick={() => setShowSettings(!showSettings)}>
            <Settings size={14} />
            AWS Settings
            {showSettings ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          {showSettings && (
            <div className="login-settings-grid">
              <label>
                <span><Server size={14} /> API URL</span>
                <input
                  value={auth.apiBaseUrl}
                  placeholder="https://api-id.execute-api.us-east-1.amazonaws.com/dev"
                  onChange={(e) => auth.setApiBaseUrl(e.target.value)}
                />
              </label>
              <label>
                <span>User Pool ID</span>
                <input
                  value={auth.userPoolId}
                  placeholder="us-east-1_example"
                  onChange={(e) => auth.setUserPoolId(e.target.value)}
                />
              </label>
              <label>
                <span>Client ID</span>
                <input
                  value={auth.clientId}
                  placeholder="Cognito app client id"
                  onChange={(e) => auth.setClientId(e.target.value)}
                />
              </label>
            </div>
          )}
        </div>

        <div className="login-legal-links" aria-label="Legal links">
          <a href="?page=privacy">Privacy</a>
          <a href="?page=terms">Terms</a>
          <a href="?page=proctoring">Proctoring notice</a>
        </div>
      </div>
    </div>
  );
}

// Keep backward-compatible export for inline usage
export function AuthPanel({ auth }: Props) {
  return <LoginPage auth={auth} />;
}
