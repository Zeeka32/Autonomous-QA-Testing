export type Provider = "gemini" | "openai" | "cohere";
export type TestStatus = "passed" | "failed" | "error" | "skipped";
export type RunStatus = "queued" | "running" | "completed" | "failed";

export type TestCase = {
  test_id: string;
  name: string;
  kind: string;
  goal: string | null;
};

export type CheckResult = {
  name: string;
  passed: boolean;
  message: string;
};

export type TestResult = {
  test_id: string;
  status: TestStatus;
  duration_ms: number;
  message: string;
  checks: CheckResult[];
};

export type Suite = {
  url: string;
  request: string | null;
  tests: TestCase[];
};

export type Run = {
  run_id: string;
  status: RunStatus;
  suite: Suite | null;
  results: TestResult[];
  suite_run: { suite: Suite; results: TestResult[] } | null;
  passed: boolean | null;
  code: string | null;
  message: string | null;
};

export type AcceptedRun = { run_id: string; status_path: string };
export type Artifact = { name: string; path: string };
export type ArtifactListing = { artifacts: Artifact[] };

export type StartRunInput = {
  url: string;
  request: string;
  provider: Provider;
};
