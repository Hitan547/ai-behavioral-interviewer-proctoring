export type Job = {
  orgId: string;
  jobId: string;
  title: string;
  jdText: string;
  minPassScore: number;
  openPositions?: number;
  shortlistThreshold?: number;
  deadline?: string | null;
  status: string;
  recruiterEmail?: string;
  createdAt?: number;
  updatedAt?: number;
};

export type Candidate = {
  orgId: string;
  jobId: string;
  candidateId: string;
  name: string;
  email: string;
  collegeName?: string;
  department?: string;
  graduationYear?: string;
  resumeFilename?: string;
  resumeS3Key?: string;
  resumeText?: string;
  matchScore?: number;
  matchReason?: string;
  shortlisted?: boolean;
  shortlistedAt?: number;
  inviteSentAt?: number;
  startedAt?: number;
  submittedAt?: number;
  latestSubmissionId?: string;
  latestResultScore?: number;
  latestRecommendation?: string;
  latestAssessmentStatus?: string;
  latestIntegrityRiskLevel?: string;
  latestIntegrityRiskScore?: number;
  latestIntegrityPenalty?: number;
  latestResultAt?: number;
  latestReportGeneratedAt?: number;
  retestCount?: number;
  lastRetestAt?: number;
  interviewStatus: string;
};

export type PreparedQuestion = {
  questionIndex: number;
  question: string;
  keywords: string[];
};

export type MatchResult = {
  filename: string;
  name: string;
  email: string;
  collegeName?: string;
  department?: string;
  graduationYear?: string;
  resumeText: string;
  matchScore: number;
  matchReason: string;
  keyMatches: string[];
  keyGaps: string[];
  rowId: string;
  selected: boolean;
  shortlisted?: boolean;
};

export type InviteResult = {
  name: string;
  email: string;
  username?: string;
  password?: string;
  status: string;
  statusIcon: string;
};

export type JobStats = {
  total: number;
  invited: number;
  inProgress: number;
  completed: number;
  passed: number;
  belowThreshold: number;
  expired: number;
};

export type ScoringResult = {
  baseScore?: number;
  finalScore: number;
  recommendation: string;
  assessmentStatus?: string;
  minPassScore?: number;
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
    answerText?: string;
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

export type BillingPlan = {
  id: string;
  name: string;
  priceLabel: string;
  amountPaise: number;
  monthlyInterviewLimit: number | null;
  features: string[];
  popular?: boolean;
  status?: string;
  trialExpiresAt?: number | null;
};

export type BillingEvent = {
  eventId: string;
  eventType: string;
  label: string;
  oldPlan?: string | null;
  newPlan?: string | null;
  provider?: string;
  providerEventId?: string | null;
  createdAt?: number;
};

export type BillingSummary = {
  organization: {
    orgId: string;
    orgName: string;
    ownerEmail?: string | null;
  };
  currentPlan: BillingPlan & {
    status: string;
    trialExpiresAt?: number | null;
  };
  usage: {
    used: number;
    limit: number | null;
    remaining: number | null;
    currentMonth: string;
    usagePercent: number;
  };
  plans: BillingPlan[];
  events: BillingEvent[];
  paymentGateway: {
    provider: "razorpay";
    configured: boolean;
  };
};
