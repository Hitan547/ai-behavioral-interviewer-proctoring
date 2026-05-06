import { KeyRound, LogOut, Server, UserRound } from "lucide-react";
import { useState } from "react";
import { claimsValue, signInWithCognito } from "./cognito";
import type { AuthSession } from "./useAuthSession";

type Props = {
  auth: AuthSession;
};

export function AuthPanel({ auth }: Props) {
  const [email, setEmail] = useState(auth.username);
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const signedIn = Boolean(auth.accessToken);

  async function signIn() {
    setStatus("");
    try {
      if (!auth.userPoolId || !auth.clientId) {
        throw new Error("Cognito user pool id and client id are required.");
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
      setStatus("Signed in.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <section className="panel auth-panel cognito-panel">
      <div className="auth-grid">
        <label>
          <span>
            <Server size={16} />
            API URL
          </span>
          <input
            value={auth.apiBaseUrl}
            placeholder="https://api-id.execute-api.us-east-1.amazonaws.com/dev"
            onChange={(event) => auth.setApiBaseUrl(event.target.value)}
          />
        </label>
        <label>
          <span>User Pool ID</span>
          <input
            value={auth.userPoolId}
            placeholder="us-east-1_example"
            onChange={(event) => auth.setUserPoolId(event.target.value)}
          />
        </label>
        <label>
          <span>Client ID</span>
          <input value={auth.clientId} placeholder="Cognito app client id" onChange={(event) => auth.setClientId(event.target.value)} />
        </label>
      </div>

      <div className="auth-grid login-row">
        <label>
          <span>
            <UserRound size={16} />
            Email
          </span>
          <input value={email} placeholder="user@example.com" onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          <span>
            <KeyRound size={16} />
            Password
          </span>
          <input
            value={password}
            type="password"
            placeholder="Cognito password"
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <div className="auth-actions">
          {signedIn ? (
            <button type="button" onClick={auth.clearSession}>
              <LogOut size={17} />
              Sign out
            </button>
          ) : (
            <button type="button" onClick={signIn}>
              <KeyRound size={17} />
              Sign in
            </button>
          )}
        </div>
      </div>

      <div className="session-line">
        <span>{signedIn ? `Signed in as ${auth.username || email}` : "Not signed in"}</span>
        <span>Org: {auth.orgId || "missing custom:org_id"}</span>
        <span>Role: {auth.role || "missing role"}</span>
        {status && <span>{status}</span>}
      </div>
    </section>
  );
}
