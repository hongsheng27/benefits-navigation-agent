export type DimKey = "bereave" | "children" | "jobless" | "money" | "rent" | "care";

export type DetectedDim = {
  key: DimKey;
  tag: string;
};

export type ChatRole = "ai" | "user";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  chips?: string[];
};

export type NavigatorStep = "chat" | "interpret" | "match" | "detail" | "profile";

export type QuestionCode =
  | "insured_type"
  | "relation"
  | "insured_years"
  | "children"
  | "employment"
  | "household";

export type EligibilityQuestion = {
  code: QuestionCode;
  label: string;
  prompt: string;
  options: string[];
  why: string;
  profileField?: string;
  mydataPrefill?: boolean;
};

export type ProfileFieldSource = "self" | "mydata" | "calc";

export type ProfileField = {
  code: string;
  label: string;
  why: string;
  value: string;
  source: ProfileFieldSource;
  options?: string[];
};

export type ProfileSectionKey = "basic" | "family" | "econ" | "status";

export type ProfileSection = {
  title: string;
  description: string;
  fields: ProfileField[];
};

export type ProfileState = Record<ProfileSectionKey, ProfileSection>;

export type MyDataSourceSet = {
  name: string;
  org: string;
  fieldCode: string;
};

export type MyDataAuthorization = {
  authorized: boolean;
  authorizedAt: string | null;
  expiresAt: string | null;
};

export type DocumentSourceType = "auto" | "mydata" | "self";

export type DocumentRequirement = {
  name: string;
  sourceType: DocumentSourceType;
  needs: QuestionCode[];
  note: string;
};

export type BenefitItem = {
  id: string;
  name: string;
  org: string;
  deadline: string | null;
  basis: string;
  location: string;
  amountLabel: string;
  requires: QuestionCode[];
  reason: string;
  plainExplanation: string;
  documents: DocumentRequirement[];
};

export type ApplyStep = {
  title: string;
  detail: string;
  isPrerequisite?: boolean;
};

export type ApplyLink = {
  label: string;
  note: string;
};

export type ApplyGuide = {
  fullDescription: string;
  authority: string;
  level: string;
  area: string;
  onlineNote: string;
  steps: ApplyStep[];
  links: ApplyLink[];
};

export type VerdictKind = "ok" | "info" | "no" | "pending";

export type EstimateResult =
  | { ok: false; reason: string }
  | {
      ok: true;
      kind: "once" | "monthly";
      amount: number;
      months?: number;
      note: string;
      exact: boolean;
    };

export type NoReasonInfo = {
  condition: string;
  mine: string;
  need: string;
};

export type DocumentSourceInfo = {
  org: string;
  linkLabel: string;
};
