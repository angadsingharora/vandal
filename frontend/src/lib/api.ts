// The war room's view of the backend (backend/vandal/api). One interface, two implementations:
// HTTP against FastAPI, or the in-browser mock (src/mock) recorded from the real backend.

import type {
  Actor,
  Approvals,
  CEGISResult,
  Chain,
  DiagnoseOut,
  Entities,
  EvidencePack,
  Explanation,
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
  RunSummary,
  SearchResult,
  Settings,
  ThreatPlan,
} from "./types";

export type Handlers = Record<string, (data: any) => void>;

export interface SearchBody {
  policy: string;
  scenario: string;
  depth: number;
}

export interface SynthesizeBody {
  search_id: string;
  no_llm: boolean;
  depth?: number;
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

  reset(policy: string): Promise<RunSummary>;
  createRun(policy: string): Promise<RunSummary>;
  state(runId: string): Promise<RunSummary>;
  /** O1: the planted messy documents, what intake read, and delivering one to the LLM Operator. */
  documents(runId: string): Promise<MessyDocument[]>;
  deliver(runId: string, documentId: string): Promise<DeliverOut>;
  intake(runId: string): Promise<IntakeRead[]>;
  entities(runId: string): Promise<Entities>;
  ledger(runId: string): Promise<JournalEntry[]>;
  chain(runId: string, payment: string): Promise<Chain>;
  operate(runId: string, days: number): Promise<Job>;
  replay(moves: Move[], policy: string, labels?: OracleLabel[]): Promise<ReplayOut>;

  job<R>(id: string): Promise<Job<R>>;
  search(body: SearchBody): Promise<Job<SearchResult>>;
  diagnose(searchId: string): Promise<DiagnoseOut>;
  synthesize(body: SynthesizeBody): Promise<Job<CEGISResult>>;
  verify(synthesisId: string, depth: number): Promise<Job<EvidencePack>>;
  metrics(policies: string[], depth?: number): Promise<Metrics>;
  inject(runId: string, body: InjectBody & { dry_run: true }): Promise<{ plan: ThreatPlan }>;
  inject(runId: string, body: InjectBody): Promise<Job<InjectResult>>;

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
      res = await fetch(this.base + path, {
        method,
        headers: body === undefined ? undefined : { "Content-Type": "application/json" },
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

  reset = (policy: string) => this.call<RunSummary>("POST", "/demo/reset", { policy });
  createRun = (policy: string) => this.call<RunSummary>("POST", "/runs", { policy });
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
  replay = (moves: Move[], policy: string, labels: OracleLabel[] = []) =>
    this.call<ReplayOut>("POST", "/replay", { moves, policy, labels });

  job = <R>(id: string) => this.call<Job<R>>("GET", `/jobs/${id}`);
  search = (body: SearchBody) => this.call<Job<SearchResult>>("POST", "/search", body);
  diagnose = (searchId: string) =>
    this.call<DiagnoseOut>("POST", "/diagnose", { search_id: searchId });
  synthesize = (body: SynthesizeBody) =>
    this.call<Job<CEGISResult>>("POST", "/synthesize", body);
  verify = (synthesisId: string, depth: number) =>
    this.call<Job<EvidencePack>>("POST", "/verify", { synthesis_id: synthesisId, depth });
  metrics = (policies: string[], depth = 1) =>
    this.call<Metrics>(
      "GET",
      `/metrics?policies=${encodeURIComponent(policies.join(","))}&depth=${depth}`,
    );
  inject = ((runId: string, body: InjectBody) =>
    this.call("POST", `/runs/${runId}/inject`, body)) as VandalApi["inject"];

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

export async function getApi(): Promise<VandalApi> {
  if (instance) return instance;
  if (process.env.NEXT_PUBLIC_VANDAL_MOCK === "1") {
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
