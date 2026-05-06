export type Job = {
  orgId: string;
  jobId: string;
  title: string;
  jdText: string;
  minPassScore: number;
  deadline?: string | null;
  status: string;
};

export type Candidate = {
  orgId: string;
  jobId: string;
  candidateId: string;
  name: string;
  email: string;
  resumeFilename?: string;
  resumeS3Key?: string;
  interviewStatus: string;
};

export type PreparedQuestion = {
  questionIndex: number;
  question: string;
  keywords: string[];
};

export type ScoringResult = {
  finalScore: number;
  recommendation: string;
  summary: string;
  integrityRisk: {
    level: string;
    scorePenalty: number;
    tabSwitches: number;
    fullscreenExits: number;
    copyPasteAttempts: number;
    devtoolsAttempts: number;
    faceNotDetected?: number;
    multipleFaces?: number;
    eventCount: number;
  };
  perQuestion: Array<{
    questionIndex: number;
    question: string;
    answered: boolean;
    score: number;
    verdict: string;
    summary: string;
    method?: string;
    dimensions?: {
      clarity: number;
      relevance: number;
      starQuality: number;
      specificity: number;
      communication: number;
      jobFit: number;
    };
    keyStrength?: string;
    keyImprovement?: string;
    recruiterVerdict?: string;
    starDetected?: boolean;
  }>;
  reportDownload?: {
    method: "GET";
    url: string;
    expiresIn: number;
    contentType: string;
  };
};
