import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  type CognitoUserSession,
} from "amazon-cognito-identity-js";

export type CognitoConfig = {
  userPoolId: string;
  clientId: string;
};

export type CognitoLoginResult = {
  accessToken: string;
  idToken: string;
  refreshToken: string;
  claims: Record<string, unknown>;
};

export function signInWithCognito(
  config: CognitoConfig,
  username: string,
  password: string,
): Promise<CognitoLoginResult> {
  const userPool = new CognitoUserPool({
    UserPoolId: config.userPoolId,
    ClientId: config.clientId,
  });
  const user = new CognitoUser({
    Username: username,
    Pool: userPool,
  });
  const authDetails = new AuthenticationDetails({
    Username: username,
    Password: password,
  });

  return new Promise((resolve, reject) => {
    user.authenticateUser(authDetails, {
      onSuccess(session: CognitoUserSession) {
        resolve({
          accessToken: session.getAccessToken().getJwtToken(),
          idToken: session.getIdToken().getJwtToken(),
          refreshToken: session.getRefreshToken().getToken(),
          claims: session.getIdToken().decodePayload() as Record<string, unknown>,
        });
      },
      onFailure(error) {
        reject(error);
      },
      newPasswordRequired() {
        reject(new Error("A new password is required. Complete password setup in Cognito first."));
      },
    });
  });
}

export function claimsValue(claims: Record<string, unknown>, names: string[], fallback = ""): string {
  for (const name of names) {
    const value = claims[name];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return fallback;
}
