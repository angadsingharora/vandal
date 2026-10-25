"use client";

// The war room's state and the demo loop's actions: operate → search → diagnose → synthesize →
// verify → approve → apply → replay. Every number shown comes from the backend; the store only
// remembers which job or run each panel is looking at.

import { create } from "zustand";
import { ApiError, getApi, type Handlers, type InjectBody, type VandalApi } from "./api";
import { landingStage, loopSteps, sideOf, type LoopInput, type Stage } from "./loop";
import type {
  Actor,
  AlertItem,
  Approvals,
  CEGISResult,
  Chain,
  CheckResult,
  Diagnosis,
  Entities,
  EvidencePack,
  Explanation,
  Finding,
  HuntAttempt,
  HuntResult,
  InjectResult,
  IntakeRead,
  Job,
  JournalEntry,
  LogEntry,
  MessyDocument,
  Metrics,
  OracleLabel,
  PatchRequest,
  PolicyInfo,
  ReplayOut,
  RunSummary,
  SearchResult,
  Settings,
  ThreatPlan,
  VandalEvent,
  VerdictItem,
} from "./types";

export const OPERATOR: Actor = { id: "OP-1", role: "operator" };
export const CONTROLLER: Actor = { id: "U-CTRL", role: "approver" };
export const CFO: Actor = { id: "U-CFO", role: "approver" };
export const SYNTHESIZER: Actor = { id: "U-SYNTH", role: "synthesizer" };

const FEED_CAP = 400;

export type Phase = "idle" | "running" | "done" | "failed";

/** The two sides of the war room: Red attacks a clone in the sandbox, Blue guards the live path. */
export type View = "red" | "blue";

export interface RunTab {
  id: string;
  label: string;
  policy: string;
  kind: "live" | "replay";
}

/** The counterexample the loop is working on: from a search, or from an injected threat. */
export interface Attack {
  jobId: string;
  source: "search" | "inject" | "hunt";
  policy: string;
  finding: Finding;
  labels: OracleLabel[];
}

interface State {
  api: VandalApi | null;
  ready: boolean;
  error: string | null;
  settings: Settings | null;
  judge: boolean;
  view: View;
  /** The page of the loop being looked at. Its side is `view`. */
  stage: Stage;
  policies: PolicyInfo[];

  tabs: RunTab[];
  liveRunId: string | null;
  focusRunId: string | null;
  summary: RunSummary | null;
  entities: Entities | null;
  ledger: JournalEntry[];
  verdicts: VerdictItem[];
  alerts: AlertItem[];
  activity: VandalEvent[];

  operate: { phase: Phase; day: number | null; events: number | null };
  /** O1: the documents the LLM Operator can receive, and what intake read. */
  documents: MessyDocument[];
  intake: IntakeRead[];
  delivering: Phase;
  search: {
    phase: Phase;
    scenario: string;
    depth: number;
    jobId: string | null;
    explored: number;
    atDepth: number;
    result: SearchResult | null;
  };
  attack: Attack | null;
  diagnosis: { phase: Phase; data: Diagnosis | null; reason: string | null };
  chain: { payment: string | null; data: Chain | null; runId: string | null };
  synth: {
    phase: Phase;
    jobId: string | null;
    log: LogEntry[];
    result: CEGISResult | null;
    noLlm: boolean;
    depth: number;
  };
  verify: { phase: Phase; jobId: string | null; checks: CheckResult[]; pack: EvidencePack | null };
  patch: PatchRequest | null;
  appliedPolicy: string | null;
  approvals: Approvals;
  replays: { before: ReplayOut | null; after: ReplayOut | null };
  inject: { phase: Phase; plan: ThreatPlan | null; jobId: string | null; result: InjectResult | null };
  /** R13: the hunt. Its attempts stream in one at a time. */
  hunt: { phase: Phase; jobId: string | null; attempts: HuntAttempt[]; result: HuntResult | null };
  metrics: { phase: Phase; data: Metrics | null };
  explanation: { phase: Phase; data: Explanation | null; subject: string | null };
}

interface Actions {
  init(): Promise<void>;
  clearError(): void;
  toggleJudge(): void;
  setView(view: View): Promise<void>;
  setStage(stage: Stage): Promise<void>;
  /** Which steps of the loop are done, for the stepper and the pages. */
  progress(): LoopInput;
  setPlayback(on: boolean): Promise<void>;
  reset(policy: string): Promise<void>;
  loadIntake(): Promise<void>;
  deliverDocument(documentId: string): Promise<void>;
  operateDays(days: number): Promise<void>;
  focus(runId: string): Promise<void>;
  refresh(): Promise<void>;
  setSearch(p: Partial<Pick<State["search"], "depth">>): void;
  runSearch(): Promise<void>;
  replayAttack(policy: string): Promise<void>;
  diagnose(): Promise<void>;
  selectPayment(payment: string): Promise<void>;
  setNoLlm(on: boolean): void;
  setSynthDepth(depth: number): void;
  synthesize(): Promise<void>;
  verifyChoice(): Promise<void>;
  submitPatch(): Promise<void>;
  decidePatch(actor: Actor, approve: boolean, reason?: string): Promise<void>;
  applyPatch(): Promise<void>;
  loadApprovals(): Promise<void>;
  decidePayment(runId: string, requestId: string, actor: Actor, approve: boolean): Promise<string>;
  previewInject(body: InjectBody): Promise<void>;
  runInject(body: InjectBody): Promise<void>;
  runHunt(attempts?: number): Promise<void>;
  loadMetrics(policies: string[]): Promise<void>;
  explain(entityType: string, id: string, question?: string): Promise<void>;
  closeExplanation(): void;
}

export type WarRoom = State & Actions;

const idle = { phase: "idle" as Phase };

let stopRunStreams: (() => void) | null = null;
let initializing: Promise<void> | null = null; // React StrictMode mounts twice in dev

function follow(api: VandalApi, path: string, handlers: Handlers): Promise<void> {
  return new Promise((resolve) => {
    api.stream(path, handlers, resolve);
  });
}

async function finished<R>(api: VandalApi, jobId: string, handlers: Handlers): Promise<Job<R>> {
  await follow(api, `/jobs/${jobId}/events`, handlers);
  const job = await api.job<R>(jobId);
  if (job.status === "failed") throw new Error(job.error ?? `${jobId} failed`);
  return job;
}

function throttle(fn: () => void, ms: number): () => void {
  let last = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  return () => {
    const wait = last + ms - Date.now();
    if (wait <= 0) {
      last = Date.now();
      fn();
    } else if (!timer) {
      timer = setTimeout(() => {
        timer = null;
        last = Date.now();
        fn();
      }, wait);
    }
  };
}

export const useWarRoom = create<WarRoom>()((set, get) => {
  const api = () => {
    const a = get().api;
    if (!a) throw new Error("API not ready");
    return a;
  };

  /** Run an action; show its error in the banner instead of throwing. */
  const guard =
    <A extends unknown[]>(fn: (...args: A) => Promise<void>) =>
    async (...args: A) => {
      try {
        await fn(...args);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404 && /^no run /.test(err.message) && get().ready) {
          // The backend keeps runs in memory: after a restart the tab's run is gone. Start over on
          // a fresh one rather than leaving every button failing with "no run".
          const policy = get().tabs.find((t) => t.kind === "live")?.policy ?? "v0";
          await recover(policy);
          return;
        }
        set({ error: err instanceof Error ? err.message : String(err) });
      }
    };

  let recovering: Promise<void> | null = null;
  const recover = (policy: string) =>
    (recovering ??= get()
      .reset(policy)
      .then(() => set({ error: `The backend restarted, so its runs were lost. Started a fresh run under ${policy}.` }))
      .finally(() => {
        recovering = null;
      }));

  const openRunStreams = (runId: string) => {
    stopRunStreams?.();
    const a = api();
    const stops = [
      a.stream(`/runs/${runId}/verdicts`, {
        verdict: (v: VerdictItem) =>
          set((s) => (s.focusRunId === runId ? { verdicts: [...s.verdicts, v].slice(-FEED_CAP) } : {})),
        alert: (al: AlertItem) =>
          set((s) => (s.focusRunId === runId ? { alerts: [...s.alerts, al].slice(-FEED_CAP) } : {})),
      }),
      a.stream(`/runs/${runId}/events`, {
        event: (e: VandalEvent) => {
          if (e.kind === "gate.verdict") return;
          set((s) => (s.focusRunId === runId ? { activity: [...s.activity, e].slice(-FEED_CAP) } : {}));
        },
      }),
    ];
    stopRunStreams = () => stops.forEach((stop) => stop());
  };

  const addTab = (tab: RunTab) => set((s) => ({ tabs: [...s.tabs.filter((t) => t.id !== tab.id), tab] }));

  return {
    api: null,
    ready: false,
    error: null,
    settings: null,
    judge: false,
    view: "blue",
    stage: "operate",
    policies: [],
    tabs: [],
    liveRunId: null,
    focusRunId: null,
    summary: null,
    entities: null,
    ledger: [],
    verdicts: [],
    alerts: [],
    activity: [],
    operate: { ...idle, day: null, events: null },
    documents: [],
    intake: [],
    delivering: "idle",
    // "all": one strike searches every threat family; the result names the family that broke first
    search: { ...idle, scenario: "all", depth: 3, jobId: null, explored: 0, atDepth: 0, result: null },
    attack: null,
    diagnosis: { ...idle, data: null, reason: null },
    chain: { payment: null, data: null, runId: null },
    synth: { ...idle, jobId: null, log: [], result: null, noLlm: true, depth: 2 },
    verify: { ...idle, jobId: null, checks: [], pack: null },
    patch: null,
    appliedPolicy: null,
    approvals: { payments: [], patches: [] },
    replays: { before: null, after: null },
    inject: { ...idle, plan: null, jobId: null, result: null },
    hunt: { ...idle, jobId: null, attempts: [], result: null },
    metrics: { ...idle, data: null },
    explanation: { ...idle, data: null, subject: null },

    init: guard(async () => {
      if (get().ready) return;
      initializing ??= (async () => {
        const a = await getApi();
        set({ api: a });
        const [settings, policies] = await Promise.all([a.settings(), a.policies()]);
        // Ask Claude when it can answer (a key, or recordings in playback); sweep otherwise.
        const noLlm = !(settings.api_key || settings.playback);
        set((st) => ({ settings, policies, synth: { ...st.synth, noLlm } }));
        await get().reset("v0");
        set({ ready: true });
      })().finally(() => {
        initializing = null;
      });
      await initializing;
    }),

    clearError: () => set({ error: null }),
    toggleJudge: () => set((s) => ({ judge: !s.judge })),

    progress: () => {
      const s = get();
      return {
        operated: s.operate.phase === "done",
        attacked: !!s.attack,
        diagnosed: s.diagnosis.phase === "done" && !!s.diagnosis.data,
        synthesized: !!s.synth.result?.policy,
        submitted: !!s.patch,
        applied: !!s.appliedPolicy,
        enforced: !!s.replays.after,
      };
    },

    // Switching sides opens that side's current page.
    setView: async (view: View) => {
      await get().setStage(landingStage(loopSteps(get().progress()), view));
    },

    // Blue's pages watch the live run (Enforce: the replay under the new policy, once there is
    // one); Red's look at the latest sandbox clone of the attack, or the live run it clones.
    setStage: guard(async (stage: Stage) => {
      const view = sideOf(stage);
      set({ stage, view });
      const { tabs, liveRunId, focusRunId, replays } = get();
      const afterId = replays.after?.run.run_id ?? null;
      const target =
        stage === "enforce"
          ? (afterId ?? liveRunId)
          : view === "blue"
            ? liveRunId
            : (tabs.filter((t) => t.kind === "replay" && t.id !== afterId).at(-1)?.id ?? liveRunId);
      if (target && target !== focusRunId) await get().focus(target);
    }),

    setPlayback: guard(async (on: boolean) => {
      set({ settings: await api().setSettings({ playback: on }) });
    }),

    loadIntake: guard(async () => {
      const runId = get().focusRunId;
      if (!runId) {
        set({ documents: [], intake: [] });
        return;
      }
      const a = api();
      const [documents, intake] = await Promise.all([a.documents(runId), a.intake(runId)]);
      if (get().focusRunId === runId) set({ documents, intake });
    }),

    deliverDocument: guard(async (documentId: string) => {
      const runId = get().focusRunId;
      if (!runId) return;
      set({ delivering: "running" });
      try {
        await api().deliver(runId, documentId);
        set({ delivering: "done" });
      } catch (err) {
        set({ delivering: "failed" });
        throw err;
      } finally {
        await get().refresh();
        await get().loadIntake();
      }
    }),

    // The demo has one path: a reset starts over on Blue at step 1.
    reset: guard(async (policy: string) => {
      const a = api();
      const run = await a.reset(policy);
      set({
        view: "blue",
        tabs: [{ id: run.run_id, label: "Live", policy: run.policy, kind: "live" }],
        liveRunId: run.run_id,
        documents: [],
        intake: [],
        delivering: "idle",
        operate: { ...idle, day: null, events: null },
        search: { ...get().search, ...idle, jobId: null, explored: 0, atDepth: 0, result: null },
        attack: null,
        diagnosis: { ...idle, data: null, reason: null },
        chain: { payment: null, data: null, runId: null },
        synth: { ...get().synth, ...idle, jobId: null, log: [], result: null },
        verify: { ...idle, jobId: null, checks: [], pack: null },
        patch: null,
        appliedPolicy: null,
        replays: { before: null, after: null },
        inject: { ...idle, plan: null, jobId: null, result: null },
        hunt: { ...idle, jobId: null, attempts: [], result: null },
        explanation: { ...idle, data: null, subject: null },
        policies: await a.policies(),
        stage: "operate",
      });
      await get().focus(run.run_id);
      await get().loadApprovals();
    }),

    focus: guard(async (runId: string) => {
      set({ focusRunId: runId, verdicts: [], alerts: [], activity: [], summary: null, entities: null, ledger: [] });
      openRunStreams(runId);
      await get().refresh();
    }),

    refresh: guard(async () => {
      const runId = get().focusRunId;
      if (!runId) return;
      const a = api();
      const [summary, entities, ledger] = await Promise.all([a.state(runId), a.entities(runId), a.ledger(runId)]);
      if (get().focusRunId === runId) set({ summary, entities, ledger });
      if (get().documents.length === 0) await get().loadIntake();
    }),

    operateDays: guard(async (days: number) => {
      const a = api();
      const runId = get().liveRunId;
      if (!runId) return;
      if (get().focusRunId !== runId) await get().focus(runId);
      set({ operate: { phase: "running", day: null, events: null } });
      const refresh = throttle(() => void get().refresh(), 800);
      try {
        const job = await a.operate(runId, days);
        await finished(a, job.id, {
          progress: (p: { day: number; events: number }) => {
            set({ operate: { phase: "running", day: p.day, events: p.events } });
            refresh();
          },
        });
        set((s) => ({ operate: { ...s.operate, phase: "done" } }));
      } catch (err) {
        set((s) => ({ operate: { ...s.operate, phase: "failed" } }));
        throw err;
      } finally {
        await get().refresh();
        await get().loadApprovals();
      }
    }),

    setSearch: (p) => set((s) => ({ search: { ...s.search, ...p } })),

    runSearch: guard(async () => {
      const a = api();
      const { scenario, depth } = get().search;
      const policy = get().summary?.policy ?? "v0";
      set({
        search: { ...get().search, phase: "running", explored: 0, atDepth: 0, result: null, jobId: null },
        diagnosis: { ...idle, data: null, reason: null },
      });
      try {
        const job = await a.search({ policy, scenario, depth });
        set((s) => ({ search: { ...s.search, jobId: job.id } }));
        const done = await finished<SearchResult>(a, job.id, {
          progress: (p: { depth: number; explored: number }) =>
            set((s) => ({ search: { ...s.search, explored: p.explored, atDepth: p.depth } })),
        });
        const result = done.result!;
        set((s) => ({
          search: { ...s.search, phase: "done", result, explored: result.explored },
          attack: result.best
            ? { jobId: job.id, source: "search", policy, finding: result.best, labels: [] }
            : s.attack,
        }));
      } catch (err) {
        set((s) => ({ search: { ...s.search, phase: "failed" } }));
        throw err;
      }
      // Show the attack on a fresh clone right away: its books, and the message that did it.
      if (get().search.result?.best) await get().replayAttack(policy);
    }),

    replayAttack: guard(async (policy: string) => {
      const attack = get().attack;
      if (!attack) return;
      const out = await api().replay(attack.finding.moves, policy, attack.labels);
      const before = policy === attack.policy;
      set((s) => ({ replays: { ...s.replays, [before ? "before" : "after"]: out } }));
      addTab({
        id: out.run.run_id,
        label: `${before ? "Attack" : "Replay"} · ${policy}`,
        policy,
        kind: "replay",
      });
      await get().focus(out.run.run_id);
      const pay = out.result.violations.find((v) => v.subject.startsWith("PAY-"))?.subject;
      const diag = get().diagnosis.data?.payment;
      const target = pay ?? diag;
      if (target && get().entities?.payments.some((p) => p.id === target)) await get().selectPayment(target);
    }),

    diagnose: guard(async () => {
      const attack = get().attack;
      if (!attack) return;
      set({ diagnosis: { phase: "running", data: null, reason: null } });
      try {
        const out = await api().diagnose(attack.jobId);
        set({ diagnosis: { phase: "done", data: out.diagnosis, reason: out.reason ?? null } });
        if (out.diagnosis) {
          set({ chain: { payment: out.diagnosis.payment, data: out.diagnosis.chain, runId: null } });
        }
      } catch (err) {
        set({ diagnosis: { phase: "failed", data: null, reason: null } });
        throw err;
      }
    }),

    selectPayment: guard(async (payment: string) => {
      const runId = get().focusRunId;
      if (!runId) return;
      set({ chain: { payment, data: null, runId } });
      const data = await api().chain(runId, payment);
      if (get().chain.payment === payment) set({ chain: { payment, data, runId } });
    }),

    setNoLlm: (on) => set((s) => ({ synth: { ...s.synth, noLlm: on } })),
    setSynthDepth: (depth) => set((s) => ({ synth: { ...s.synth, depth } })),

    synthesize: guard(async () => {
      const a = api();
      const attack = get().attack;
      if (!attack) return;
      set((s) => ({
        synth: { ...s.synth, phase: "running", log: [], result: null, jobId: null },
        verify: { ...idle, jobId: null, checks: [], pack: null },
        patch: null,
      }));
      const { noLlm, depth } = get().synth;
      try {
        const job = await a.synthesize({ search_id: attack.jobId, no_llm: noLlm, depth });
        set((s) => ({ synth: { ...s.synth, jobId: job.id } }));
        const done = await finished<CEGISResult>(a, job.id, {
          log: (e: LogEntry) => set((s) => ({ synth: { ...s.synth, log: [...s.synth.log, e] } })),
        });
        set((s) => ({ synth: { ...s.synth, phase: "done", result: done.result!, log: done.result!.log } }));
      } catch (err) {
        set((s) => ({ synth: { ...s.synth, phase: "failed" } }));
        throw err;
      }
    }),

    verifyChoice: guard(async () => {
      const a = api();
      const synthId = get().synth.jobId;
      if (!synthId) return;
      set({ verify: { phase: "running", jobId: null, checks: [], pack: null }, patch: null });
      try {
        const job = await a.verify(synthId, get().synth.depth); // prove it at the depth CEGIS used
        set((s) => ({ verify: { ...s.verify, jobId: job.id } }));
        const done = await finished<EvidencePack>(a, job.id, {
          check: (c: CheckResult) => set((s) => ({ verify: { ...s.verify, checks: [...s.verify.checks, c] } })),
        });
        set((s) => ({ verify: { ...s.verify, phase: "done", pack: done.result!, checks: done.result!.checks } }));
      } catch (err) {
        set((s) => ({ verify: { ...s.verify, phase: "failed" } }));
        throw err;
      }
    }),

    // The fix crosses to Blue: the war room follows it to the Approve page.
    submitPatch: guard(async () => {
      const jobId = get().verify.jobId;
      if (!jobId) return;
      set({ patch: await api().submitPatch(jobId, SYNTHESIZER) });
      await get().loadApprovals();
      await get().setStage("approve");
    }),

    decidePatch: guard(async (actor: Actor, approve: boolean, reason = "") => {
      const patch = get().patch;
      if (!patch) return;
      set({ patch: await api().decidePatch(patch.id, actor, approve, reason) });
      await get().loadApprovals();
    }),

    applyPatch: guard(async () => {
      const a = api();
      const patch = get().patch;
      if (!patch) return;
      await a.applyPolicy(patch.version);
      set({ patch: { ...patch, status: "applied" }, appliedPolicy: patch.version, policies: await a.policies() });
      await get().loadApprovals();
      await get().setStage("enforce");
    }),

    loadApprovals: guard(async () => {
      set({ approvals: await api().approvals() });
    }),

    decidePayment: async (runId, requestId, actor, approve) => {
      try {
        const out = await api().decidePayment(runId, requestId, actor, approve);
        await get().loadApprovals();
        await get().refresh();
        return out.ok ? `${approve ? "approved" : "denied"} by ${actor.id}` : `Guard ${out.decision}: ${out.error ?? out.fired.join(", ")}`;
      } catch (err) {
        return err instanceof Error ? err.message : String(err);
      }
    },

    // Inject runs on a fresh clone under the focused run's policy, which is what the dialog's
    // "Run on <policy>" button names: under v0 from the Live tab, under the synthesized policy
    // from a replay tab.
    previewInject: guard(async (body: InjectBody) => {
      const runId = get().focusRunId ?? get().liveRunId;
      if (!runId) return;
      set({ inject: { phase: "running", plan: null, jobId: null, result: null } });
      try {
        const { plan } = await api().inject(runId, { ...body, dry_run: true });
        set({ inject: { phase: "idle", plan, jobId: null, result: null } });
      } catch (err) {
        set((s) => ({ inject: { ...s.inject, phase: "failed" } }));
        throw err;
      }
    }),

    runHunt: guard(async (attempts = 6) => {
      const a = api();
      const runId = get().focusRunId;
      if (!runId) return;
      const policy = get().summary?.policy ?? "v0";
      set({
        hunt: { phase: "running", jobId: null, attempts: [], result: null },
        diagnosis: { ...idle, data: null, reason: null },
      });
      try {
        // Run every attempt, hits included: a hunt is a set of hypotheses, not a race to one.
        const job = await a.hunt(runId, { attempts, keep_going: true });
        set((s) => ({ hunt: { ...s.hunt, jobId: job.id } }));
        const done = await finished<HuntResult>(a, job.id, {
          log: (t: HuntAttempt) => set((s) => ({ hunt: { ...s.hunt, attempts: [...s.hunt.attempts, t] } })),
        });
        const result = done.result!;
        set((s) => ({
          hunt: { ...s.hunt, phase: "done", result, attempts: result.attempts },
          attack: result.best
            ? { jobId: job.id, source: "hunt", policy, finding: result.best, labels: [] }
            : s.attack,
        }));
      } catch (err) {
        set((s) => ({ hunt: { ...s.hunt, phase: "failed" } }));
        throw err;
      }
      if (get().hunt.result?.best) await get().replayAttack(policy);
    }),

    runInject: guard(async (body: InjectBody) => {
      const a = api();
      const runId = get().focusRunId ?? get().liveRunId;
      if (!runId) return;
      set((s) => ({ inject: { ...s.inject, phase: "running", jobId: null, result: null } }));
      try {
        const job = await a.inject(runId, { ...body, dry_run: false });
        set((s) => ({ inject: { ...s.inject, jobId: job.id } }));
        const done = await finished<InjectResult>(a, job.id, {});
        const result = done.result!;
        const policy = String(done.meta.policy ?? get().summary?.policy ?? "v0");
        set((s) => ({
          inject: { ...s.inject, phase: "done", plan: result.plan, result },
          attack: result.best
            ? { jobId: job.id, source: "inject", policy, finding: result.best, labels: result.labels }
            : s.attack,
          diagnosis: result.best ? { ...idle, data: null, reason: null } : s.diagnosis,
        }));
      } catch (err) {
        set((s) => ({ inject: { ...s.inject, phase: "failed" } }));
        throw err;
      }
      const atk = get().attack;
      if (get().inject.result?.best && atk) await get().replayAttack(atk.policy);
    }),

    loadMetrics: guard(async (policies: string[]) => {
      set((s) => ({ metrics: { ...s.metrics, phase: "running" } }));
      try {
        set({ metrics: { phase: "done", data: await api().metrics(policies) } });
      } catch (err) {
        set((s) => ({ metrics: { ...s.metrics, phase: "failed" } }));
        throw err;
      }
    }),

    explain: guard(async (entityType: string, id: string, question?: string) => {
      const runId = get().focusRunId;
      if (!runId) return;
      set({ explanation: { phase: "running", data: null, subject: id } });
      try {
        const data = await api().explain(entityType, id, runId, question);
        set({ explanation: { phase: "done", data, subject: id } });
      } catch (err) {
        set({ explanation: { phase: "failed", data: null, subject: id } });
        throw err;
      }
    }),

    closeExplanation: () => set({ explanation: { ...idle, data: null, subject: null } }),
  };
});
