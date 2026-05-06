import { useMemo, useState } from "react";

export type AuthSession = {
  apiBaseUrl: string;
  accessToken: string;
  idToken: string;
  userPoolId: string;
  clientId: string;
  orgId: string;
  role: string;
  username: string;
  setAccessToken: (value: string) => void;
  setIdToken: (value: string) => void;
  setApiBaseUrl: (value: string) => void;
  setUserPoolId: (value: string) => void;
  setClientId: (value: string) => void;
  setOrgId: (value: string) => void;
  setRole: (value: string) => void;
  setUsername: (value: string) => void;
  clearSession: () => void;
  authHeaders: () => HeadersInit;
};

export function useAuthSession(): AuthSession {
  const [apiBaseUrl, setApiBaseUrlState] = useState(
    localStorage.getItem("psysense.apiBaseUrl") || import.meta.env.VITE_API_BASE_URL || "",
  );
  const [accessToken, setAccessTokenState] = useState(localStorage.getItem("psysense.accessToken") || "");
  const [idToken, setIdTokenState] = useState(localStorage.getItem("psysense.idToken") || "");
  const [userPoolId, setUserPoolIdState] = useState(
    localStorage.getItem("psysense.userPoolId") || import.meta.env.VITE_COGNITO_USER_POOL_ID || "",
  );
  const [clientId, setClientIdState] = useState(
    localStorage.getItem("psysense.clientId") || import.meta.env.VITE_COGNITO_CLIENT_ID || "",
  );
  const [orgId, setOrgIdState] = useState(localStorage.getItem("psysense.orgId") || "");
  const [role, setRoleState] = useState(localStorage.getItem("psysense.role") || "recruiter");
  const [username, setUsernameState] = useState(localStorage.getItem("psysense.username") || "");

  return useMemo(
    () => ({
      apiBaseUrl,
      accessToken,
      idToken,
      userPoolId,
      clientId,
      orgId,
      role,
      username,
      setApiBaseUrl(value: string) {
        localStorage.setItem("psysense.apiBaseUrl", value.trim());
        setApiBaseUrlState(value.trim());
      },
      setAccessToken(value: string) {
        localStorage.setItem("psysense.accessToken", value.trim());
        setAccessTokenState(value.trim());
      },
      setIdToken(value: string) {
        localStorage.setItem("psysense.idToken", value.trim());
        setIdTokenState(value.trim());
      },
      setUserPoolId(value: string) {
        localStorage.setItem("psysense.userPoolId", value.trim());
        setUserPoolIdState(value.trim());
      },
      setClientId(value: string) {
        localStorage.setItem("psysense.clientId", value.trim());
        setClientIdState(value.trim());
      },
      setOrgId(value: string) {
        localStorage.setItem("psysense.orgId", value.trim());
        setOrgIdState(value.trim());
      },
      setRole(value: string) {
        localStorage.setItem("psysense.role", value.trim());
        setRoleState(value.trim());
      },
      setUsername(value: string) {
        localStorage.setItem("psysense.username", value.trim());
        setUsernameState(value.trim());
      },
      clearSession() {
        [
          "psysense.accessToken",
          "psysense.idToken",
          "psysense.orgId",
          "psysense.role",
          "psysense.username",
        ].forEach((key) => localStorage.removeItem(key));
        setAccessTokenState("");
        setIdTokenState("");
        setOrgIdState("");
        setRoleState("recruiter");
        setUsernameState("");
      },
      authHeaders() {
        return {
          Authorization: `Bearer ${idToken || accessToken}`,
          "Content-Type": "application/json",
        };
      },
    }),
    [accessToken, apiBaseUrl, clientId, idToken, orgId, role, userPoolId, username],
  );
}
