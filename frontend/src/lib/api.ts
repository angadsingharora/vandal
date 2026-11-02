// The war room's view of the backend (backend/vandal/api). One interface, two implementations:
// HTTP against FastAPI, or the in-browser mock (src/mock) recorded from the real backend.

import { clientId } from "./client";
import type {
  Actor,
  Approvals,
  CEGISResult,
  Chain,
  DiagnoseOut,
  Entities,
  EvidencePack,
  Explanation,
  GuardCheckOut,
  GuardTool,
  HuntResult,
  InjectResult,
  Job,
  JournalEntry,
  Metrics,
  Move,
  OracleLabel,
  PatchRequest,
  PaymentDecisionOut,
  PolicyInfo,
  ReplayOut,
  DeliverOut,
  IntakeRead,
  MessyDocument,
  NewProfile,
  ProfileExport,
  ProfileInfo,
  RunListItem,
  RunSummary,
  SearchResult,
  Settings,
  ThreatPlan,
} from "./types";

export type Handlers = Record<string, (data: any) => void>;

/** Which company a run (or a job's clones) is seeded from. Omitted: the backend's default. */
export interface RunOptions {
  policy: string;
  profile?: string;
  seed?: number;
}

export interface SearchBody {
  policy: string;
  scenario: string;
  depth: number;
  /** Compute even when playback would serve a recording. */
  fresh?: boolean;
  profile?: string;
  seed?: number;
  /** Parallel runs; omitted: the host's default. */
  workers?: number;
  exhaustive?: boolean;
}

export interface SynthesizeBody {
  search_id: string;
  no_llm: boolean;
  depth?: number;
  max_iterations?: number;
  workers?: number;
  profile?: string;
  seed?: number;
}

export interface VerifyBody {
  synthesis_id: string;
  depth: number;
  workers?: number;
  profile?: string;
  seed?: number;
}

export interface InjectBody {
  description?: string;
  moves?: Move[];
  labels?: OracleLabel[];
  scenario?: string;
  depth?: number;
  no_llm?: boolean;
  dry_run?: boolean;
}

export interface VandalApi {
  readonly mode: "http" | "mock";
  settings(): Promise<Settings>;
  setSettings(s: { playback: boolean }): Promise<Settings>;
  policies(): Promise<PolicyInfo[]>;
  /** The companies a run can be seeded from, and deriving a new one (the workspace's custom company). */
  profiles(): Promise<ProfileInfo[]>;
  createProfile(body: NewProfile): Promise<ProfileInfo>;
  /** The whole company as JSON, and bringing one back (a custom company is gone after a restart). */
  exportProfile(name: string): Promise<ProfileExport>;
  importProfile(body: { name?: string; profile: Record<string, unknown> }): Promise<ProfileInfo>;

  /** This client's runs on the server, oldest first. */
  listRuns(): Promise<RunListItem[]>;
  reset(opts: RunOptions): Promise<RunSummary>;
  createRun(opts: RunOptions): Promise<RunSummary>;
  state(runId: string): Promise<RunSummary>;
  /** O1: the planted messy documents, what intake read, and delivering one to the LLM Operator. */
  documents(runId: string): Promise<MessyDocument[]>;
  deliver(runId: string, documentId: string): Promise<DeliverOut>;
  intake(runId: string): Promise<IntakeRead[]>;
  entities(runId: string): Promise<Entities>;
  ledger(runId: string): Promise<JournalEntry[]>;
  chain(runId: string, payment: string): Promise<Chain>;
  operate(runId: string, days: number): Promise<Job>;
  replay(moves: Move[], policy: string, labels?: OracleLabel[], run?: Omit<RunOptions, "policy">): Promise<ReplayOut>;
  /** Guard as an API: what the gate would say to a tool call on this run's books, without making it. */
  guardTools(): Promise<GuardTool[]>;
  guardCheck(runId: string, body: { tool: string; args: Record<string, unknown>; actor?: Actor }): Promise<GuardCheckOut>;

  job<R>(id: string): Promise<Job<R>>;
  search(body: SearchBody): Promise<Job<SearchResult>>;
  diagnose(searchId: string): Promise<DiagnoseOut>;
  synthesize(body: SynthesizeBody): Promise<Job<CEGISResult>>;
  verify(body: VerifyBody): Promise<Job<EvidencePack>>;
  /** Where a finished verification's evidence pack downloads from; null when there is no file. */
  evidenceUrl(verifyJobId: string): string | null;
  metrics(policies: string[], depth?: number, run?: Omit<RunOptions, "policy">): Promise<Metrics>;
  inject(runId: string, body: InjectBody & { dry_run: true }): Promise<{ plan: ThreatPlan }>;
  inject(runId: string, body: InjectBody): Promise<Job<InjectResult>>;
  /** R13: Claude studies the run's company and reasons out attacks; each attempt streams as a log. */
  hunt(runId: string, body: { attempts: number; keep_going?: boolean }): Promise<Job<HuntResult>>;

  approvals(): Promise<Approvals>;
  decidePayment(
    runId: string,
    requestId: string,
    actor: Actor,
    approve: boolean,
    reason?: string,
  ): Promise<PaymentDecisionOut>;
  submitPatch(verifyJobId: string, submittedBy: Actor): Promise<PatchRequest>;
  decidePatch(patchId: string, actor: Actor, approve: boolean, reason?: string): Promise<PatchRequest>;
  applyPolicy(version: string): Promise<{ applied: string; patch: string; approved_by: string }>;
  explain(entityType: string, id: string, runId: string, question?: string): Promise<Explanation>;

  /** Follow an SSE channel. Returns a function that stops following. */
  stream(path: string, handlers: Handlers, onEnd?: () => void): () => void;
}

/** POST /approvals and /decide return the whole PatchRequest (with its policy); GET /approvals
 * flattens the policy to its version. The UI keeps the flat shape. */
export function toPatch(p: PatchRequest & { policy?: { version: string } }): PatchRequest {
  const { policy, ...rest } = p;
  return { ...rest, version: p.version ?? policy?.version ?? "" };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export class HttpApi implements VandalApi {
  readonly mode = "http" as const;

  constructor(readonly base: string) {}

  private async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    let res: Response;
    try {
      // Every call says which browser it is from: the API keeps runs per client (lib/client.ts).
      const headers: Record<string, string> = { "X-Vandal-Client": clientId() };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      res = await fetch(this.base + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, `can't reach the backend at ${this.base}`);
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } catch {}
      throw new ApiError(res.status, detail);
    }
    return res.json() as Promise<T>;
  }

  settings = () => this.call<Settings>("GET", "/settings");
  setSettings = (s: { playback: boolean }) => this.call<Settings>("POST", "/settings", s);
  policies = () => this.call<PolicyInfo[]>("GET", "/policies");
  profiles = () => this.call<ProfileInfo[]>("GET", "/profiles");
  createProfile = (body: NewProfile) => this.call<ProfileInfo>("POST", "/profiles", body);
  exportProfile = (name: string) => this.call<ProfileExport>("GET", `/profiles/${encodeURIComponent(name)}/export`);
  importProfile = (body: { name?: string; profile: Record<string, unknown> }) =>
    this.call<ProfileInfo>("POST", "/profiles/import", body);

  listRuns = () => this.call<RunListItem[]>("GET", "/runs");
  reset = (opts: RunOptions) => this.call<RunSummary>("POST", "/demo/reset", opts);
  createRun = (opts: RunOptions) => this.call<RunSummary>("POST", "/runs", opts);
  state = (runId: string) => this.call<RunSummary>("GET", `/runs/${runId}/state`);
  documents = (runId: string) => this.call<MessyDocument[]>("GET", `/runs/${runId}/documents`);
  deliver = (runId: string, documentId: string) =>
    this.call<DeliverOut>("POST", `/runs/${runId}/documents/${documentId}/deliver`);
  intake = (runId: string) => this.call<IntakeRead[]>("GET", `/runs/${runId}/intake`);
  entities = (runId: string) => this.call<Entities>("GET", `/runs/${runId}/entities`);
  ledger = (runId: string) => this.call<JournalEntry[]>("GET", `/runs/${runId}/ledger`);
  chain = (runId: string, payment: string) =>
    this.call<Chain>("GET", `/runs/${runId}/chain/${payment}`);
  operate = (runId: string, days: number) =>
    this.call<Job>("POST", `/runs/${runId}/operate`, { days });
  replay = (moves: Move[], policy: string, labels: OracleLabel[] = [], run: Omit<RunOptions, "policy"> = {}) =>
    this.call<ReplayOut>("POST", "/replay", { moves, policy, labels, ...run });
  guardTools = () => this.call<GuardTool[]>("GET", "/guard/tools");
  guardCheck = (runId: string, body: { tool: string; args: Record<string, unknown>; actor?: Actor }) =>
    this.call<GuardCheckOut>("POST", `/runs/${runId}/guard/check`, body);

  job = <R>(id: string) => this.call<Job<R>>("GET", `/jobs/${id}`);
  search = (body: SearchBody) => this.call<Job<SearchResult>>("POST", "/search", body);
  diagnose = (searchId: string) =>
    this.call<DiagnoseOut>("POST", "/diagnose", { search_id: searchId });
  synthesize = (body: SynthesizeBody) =>
    this.call<Job<CEGISResult>>("POST", "/synthesize", body);
  verify = (body: VerifyBody) => this.call<Job<EvidencePack>>("POST", "/verify", body);
  evidenceUrl = (verifyJobId: string) => `${this.base}/jobs/${verifyJobId}/evidence`;
  metrics = (policies: string[], depth = 1, run: Omit<RunOptions, "policy"> = {}) => {
    const q = new URLSearchParams({ policies: policies.join(","), depth: String(depth) });
    if (run.profile) q.set("profile", run.profile);
    if (run.seed != null) q.set("seed", String(run.seed));
    return this.call<Metrics>("GET", `/metrics?${q}`);
  };
  inject = ((runId: string, body: InjectBody) =>
    this.call("POST", `/runs/${runId}/inject`, body)) as VandalApi["inject"];
  hunt = (runId: string, body: { attempts: number; keep_going?: boolean }) =>
    this.call<Job<HuntResult>>("POST", `/runs/${runId}/hunt`, body);

  approvals = () => this.call<Approvals>("GET", "/approvals");
  decidePayment = (runId: string, requestId: string, actor: Actor, approve: boolean, reason = "") =>
    this.call<PaymentDecisionOut>("POST", `/runs/${runId}/approvals/${requestId}/decide`, {
      actor,
      approve,
      reason,
    });
  submitPatch = (verifyJobId: string, submittedBy: Actor) =>
    this.call<PatchRequest>("POST", "/approvals", {
      verify_job_id: verifyJobId,
      submitted_by: submittedBy,
    }).then(toPatch);
  decidePatch = (patchId: string, actor: Actor, approve: boolean, reason = "") =>
    this.call<PatchRequest>("POST", `/approvals/${patchId}/decide`, { actor, approve, reason }).then(
      toPatch,
    );
  applyPolicy = (version: string) =>
    this.call<{ applied: string; patch: string; approved_by: string }>(
      "POST",
      `/policies/${encodeURIComponent(version)}/apply`,
    );
  explain = (entityType: string, id: string, runId: string, question?: string) => {
    const q = new URLSearchParams({ run: runId });
    if (question) q.set("question", question);
    return this.call<Explanation>("GET", `/explain/${entityType}/${id}?${q}`);
  };

  stream(path: string, handlers: Handlers, onEnd?: () => void): () => void {
    const source = new EventSource(this.base + path);
    let ended = false;
    const end = () => {
      if (ended) return;
      ended = true;
      source.close();
      onEnd?.();
    };
    for (const [kind, fn] of Object.entries(handlers)) {
      source.addEventListener(kind, (e) => fn(JSON.parse((e as MessageEvent).data)));
    }
    // A job's channel ends with `done` or `error`. Close then, or EventSource would reconnect
    // to a finished stream forever.
    source.addEventListener("done", end);
    source.addEventListener("error", (e) => {
      if ((e as MessageEvent).data) end();
    });
    return () => {
      ended = true;
      source.close();
    };
  }
}

let instance: VandalApi | null = null;

/** The recorded loop (the in-browser mock) when the build asks for it, or the URL does
 * (`?mock=1`, which the welcome screen's "Watch the recorded loop" opens). */
export function wantsMock(): boolean {
  if (process.env.NEXT_PUBLIC_VANDAL_MOCK === "1") return true;
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("mock") === "1";
}

export async function getApi(): Promise<VandalApi> {
  if (instance) return instance;
  if (wantsMock()) {
    const { MockApi } = await import("@/mock/mockApi");
    instance = new MockApi();
  } else {
    instance = new HttpApi(process.env.NEXT_PUBLIC_VANDAL_API ?? "http://localhost:8000");
  }
  return instance;
}

/** Poll a job until it finishes (for jobs whose stream we don't need). */
export async function waitJob<R>(api: VandalApi, id: string, everyMs = 300): Promise<Job<R>> {
  for (;;) {
    const job = await api.job<R>(id);
    if (job.status === "done" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, everyMs));
  }
}
