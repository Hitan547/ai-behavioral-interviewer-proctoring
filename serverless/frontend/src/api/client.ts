import type { AuthSession } from "../auth/useAuthSession";
import type { BillingSummary, Candidate, Job, JobStats, ScoringResult } from "./types";

export class ApiClient {
  constructor(private readonly auth: AuthSession) {}

  async recruiterSignup(input: { email: string; password: string; orgName: string }) {
    const baseUrl = this.auth.apiBaseUrl || "http://localhost:3001";
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/auth/recruiter-signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      throw new Error(payload.error || `Recruiter signup failed: ${response.status}`);
    }
    return payload as {
      accessToken: string;
      idToken: string;
      orgId: string;
      role: "recruiter";
      username: string;
      orgName: string;
    };
  }

  async recruiterLogin(input: { email: string; password: string }) {
    const baseUrl = this.auth.apiBaseUrl || "http://localhost:3001";
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/auth/recruiter-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      throw new Error(payload.error || `Recruiter login failed: ${response.status}`);
    }
    return payload as {
      accessToken: string;
      idToken: string;
      orgId: string;
      role: "recruiter";
      username: string;
      orgName: string;
    };
  }

  async createJob(input: { title: string; jdText: string; minPassScore: number; openPositions?: number; shortlistThreshold?: number; deadline?: string }) {
    return this.request<{ job: Job }>("/jobs", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async listJobs() {
    return this.request<{ jobs: Job[] }>("/jobs");
  }

  async createCandidate(jobId: string, input: {
    name: string;
    email: string;
    resumeFilename: string;
    collegeName?: string;
    department?: string;
    graduationYear?: string;
  }) {
    return this.request<{
      candidate: Candidate;
      resumeUpload: { method: "PUT"; url: string; key: string; headers: Record<string, string> };
    }>(`/jobs/${jobId}/candidates`, {
      method: "POST",
      body: JSON.stringify({ ...input, resumeContentType: "application/pdf" }),
    });
  }

  async uploadResume(upload: { url: string; headers: Record<string, string> }, file: File) {
    const response = await fetch(upload.url, {
      method: "PUT",
      headers: upload.headers,
      body: file,
    });
    if (!response.ok) {
      throw new Error(`Resume upload failed: ${response.status}`);
    }
  }

  async listCandidates(jobId: string) {
    return this.request<{ candidates: Candidate[] }>(`/jobs/${jobId}/candidates`);
  }

  async updateCandidate(jobId: string, candidateId: string, input: {
    name?: string;
    email?: string;
    collegeName?: string;
    department?: string;
    graduationYear?: string;
    shortlisted?: boolean;
  }) {
    return this.request<{ candidate: Candidate }>(`/jobs/${jobId}/candidates/${candidateId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  }

  async prepareInterview(jobId: string, candidateId: string) {
    return this.request<{ interview: unknown }>(`/jobs/${jobId}/candidates/${candidateId}/prepare-interview`, {
      method: "POST",
      body: "{}",
    });
  }

  async getCandidateInterview(jobId: string, candidateId: string) {
    return this.request<{
      interview: {
        candidateName: string;
        questions: Array<{ questionIndex: number; question: string; keywords: string[] }>;
      };
    }>(`/jobs/${jobId}/candidates/${candidateId}/interview`);
  }

  async submitCandidateInterview(
    jobId: string,
    candidateId: string,
    input: {
      consentAccepted: boolean;
      answers: Array<{ questionIndex: number; answerText: string; durationSeconds: number; audioS3Key?: string }>;
      integritySignals: Record<string, unknown>;
    },
  ) {
    return this.request<{
      submission: unknown;
      scoring?: { started: boolean; executionArn?: string; reason?: string };
    }>(`/jobs/${jobId}/candidates/${candidateId}/interview`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async createAudioUpload(jobId: string, candidateId: string, input: { questionIndex: number; contentType: string }) {
    return this.request<{
      audioUpload: { method: "PUT"; url: string; bucket: string; key: string; headers: Record<string, string> };
    }>(`/jobs/${jobId}/candidates/${candidateId}/audio-upload-url`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async uploadAudio(upload: { url: string; headers: Record<string, string> }, blob: Blob) {
    const response = await fetch(upload.url, {
      method: "PUT",
      headers: upload.headers,
      body: blob,
    });
    if (!response.ok) {
      throw new Error(`Audio upload failed: ${response.status}`);
    }
  }

  async transcribeQuestionAudio(
    jobId: string,
    candidateId: string,
    questionIndex: number,
    input: { audioS3Bucket: string; audioS3Key: string; contentType: string },
  ) {
    return this.request<{
      transcription: { transcript: string; audioS3Key: string; questionIndex: number };
    }>(`/jobs/${jobId}/candidates/${candidateId}/questions/${questionIndex}/transcribe`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async transcribePracticeAudio(input: {
    audioBase64: string;
    filename: string;
    contentType: string;
    questionIndex: number;
    prompt?: string;
  }) {
    return this.request<{
      transcription: { transcript: string; questionIndex: number; contentType: string };
    }>("/transcribe-practice", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async startScoring(jobId: string, candidateId: string) {
    return this.request<{ message: string; executionArn?: string }>(`/jobs/${jobId}/candidates/${candidateId}/score`, {
      method: "POST",
      body: "{}",
    });
  }

  async sendInvite(jobId: string, candidateId: string) {
    return this.request<{
      message: string;
      interviewUrl: string;
      sent: boolean;
      username?: string;
      password?: string;
      provider?: string;
    }>(`/jobs/${jobId}/candidates/${candidateId}/invite`, {
      method: "PUT",
      body: "{}",
    });
  }

  async allowRetest(jobId: string, candidateId: string) {
    return this.request<{
      message: string;
      interviewUrl: string;
      username?: string;
      password?: string;
      auditEventId?: string;
      provider?: string;
    }>(`/jobs/${jobId}/candidates/${candidateId}/retest`, {
      method: "POST",
      body: "{}",
    });
  }

  async candidateLogin(input: { username: string; password: string; orgId?: string; jobId?: string; candidateId?: string }) {
    const baseUrl = this.auth.apiBaseUrl || "http://localhost:3001";
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/auth/candidate-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      throw new Error(payload.error || `Candidate login failed: ${response.status}`);
    }
    return payload as {
      accessToken: string;
      idToken: string;
      orgId: string;
      role: "candidate";
      username: string;
      jobId: string;
      candidateId: string;
      candidateName: string;
    };
  }

  async getResult(jobId: string, candidateId: string) {
    return this.request<{ result: ScoringResult }>(`/jobs/${jobId}/candidates/${candidateId}/result`);
  }

  async analyseResumes(jobId: string) {
    return this.request<{ results: Array<{
      candidateId: string;
      name: string;
      email: string;
      collegeName?: string;
      department?: string;
      graduationYear?: string;
      resumeText?: string;
      matchScore: number;
      matchReason: string;
      keyMatches: string[];
      keyGaps: string[];
      shortlisted?: boolean;
    }> }>(`/jobs/${jobId}/analyse-resumes`, {
      method: "POST",
      body: "{}",
    });
  }

  async closeJob(jobId: string) {
    return this.request<{ job: Job }>(`/jobs/${jobId}`, {
      method: "PUT",
      body: JSON.stringify({ status: "Closed" }),
    });
  }

  async getJobStats(jobId: string) {
    return this.request<{ stats: JobStats }>(`/jobs/${jobId}/stats`);
  }

  async getBilling() {
    return this.request<{ billing: BillingSummary }>("/billing");
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.auth.apiBaseUrl) {
      throw new Error("API URL is required.");
    }
    if (!this.auth.accessToken) {
      throw new Error("Cognito access token is required.");
    }
    const response = await fetch(`${this.auth.apiBaseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: {
        ...this.auth.authHeaders(),
        ...(init.headers ?? {}),
      },
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      if (response.status === 401) {
        this.auth.clearSession();
        throw new Error("Your session expired. Please sign in again.");
      }
      throw new Error(payload.error || `Request failed: ${response.status}`);
    }
    return payload as T;
  }
}
