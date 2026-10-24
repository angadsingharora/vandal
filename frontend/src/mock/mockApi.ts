// F0: the in-browser mock API. Every response is recorded from the real backend
// (scripts/capture_fixtures.py writes fixtures.json), so shapes match; the mock only replays them
// with delays and keeps the little state the demo loop needs (runs, jobs, the inbox).

import { ApiError, toPatch, type Handlers, type InjectBody, type SearchBody, type SynthesizeBody, type VandalApi } from "@/lib/api";
import type {
  Actor,
  Approvals,
  Chain,
  DeliverOut,
  Entities,
  IntakeRead,
  Job,
  MessyDocument,
  Move,
  OperatorKind,
  OracleLabel,
  PatchRequest,
  ReplayOut,
  RunSummary,
  Settings,
} from "@/lib/types";
import fx from "./fixtures.json";

type Message = { event: string; data: unknown };
const F = fx as any;
const clone = <T>(v: T): T => structuredClone(v);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

class Channel {
  messages: Message[] = [];
  closed = false;
  private subs = new Set<() => void>();

  publish(event: string, data: unknown) {
    this.messages.push({ event, data });
    this.subs.forEach((fn) => fn());
  }

  close() {
    this.closed = true;
    this.subs.forEach((fn) => fn());
  }

  follow(handlers: Handlers, onEnd?: () => void): () => void {
    let cursor = 0;
    let stopped = false;
    const pump = () => {
      while (!stopped && cursor < this.messages.length) {
        const m = this.messages[cursor++];
        handlers[m.event]?.(m.data);
      }
      if (!stopped && this.closed) {
        stopped = true;
        this.subs.delete(pump);
        onEnd?.();
      }
    };
    this.subs.add(pump);
    queueMicrotask(pump);
    return () => {
      stopped = true;
      this.subs.delete(pump);
    };
  }
}

interface MockRun {
  summary: RunSummary;
  entities: Entities;
  events: Channel;
  verdicts: Channel;
}

interface MockJob {
  job: Job;
  channel: Channel;
}

let counter = 0;
const nextId = (prefix: string) => `${prefix}-mock${(++counter).toString().padStart(4, "0")}`;

export class MockApi implements VandalApi {
  readonly mode = "mock" as const;
  private runs = new Map<string, MockRun>();
  private jobs = new Map<string, MockJob>();
  private patches = new Map<string, PatchRequest>();
  private applied = new Set<string>();
  private playback = false;

  // --- plumbing ---------------------------------------------------------------------------

  private newRun(summary: RunSummary, entities: Entities, verdicts: Message[] = []): MockRun {
    const id = nextId("run");
    const run: MockRun = {
      summary: { ...clone(summary), run_id: id },
      entities: { ...clone(entities), run_id: id },
      events: new Channel(),
      verdicts: new Channel(),
    };
    verdicts.forEach((m) => run.verdicts.publish(m.event, m.data));
    this.runs.set(id, run);
    return run;
  }

  private run(id: string): MockRun {
    const run = this.runs.get(id);
    if (!run) throw new ApiError(404, `no run ${id}`);
    return run;
  }

  private submit<R>(kind: string, meta: Record<string, unknown>, work: (ch: Channel) => Promise<R>): Job<R> {
    const job: Job = { id: nextId(kind), kind, status: "queued", error: null, meta, messages: 0 };
    const channel = new Channel();
    this.jobs.set(job.id, { job, channel });
    (async () => {
      await sleep(50);
      job.status = "running";
      channel.publish("status", { status: "running" });
      try {
        job.result = await work(channel);
        job.status = "done";
        channel.publish("done", { status: "done" });
      } catch (err) {
        job.status = "failed";
        job.error = String(err);
        channel.publish("error", { error: job.error });
      }
      channel.close();
    })();
    return clone(job) as Job<R>;
  }

  private async replayMessages(ch: Channel, messages: Message[], totalMs: number) {
    const body = messages.filter((m) => m.event !== "status" && m.event !== "done");
    for (const m of body) {
      ch.publish(m.event, m.data);
      await sleep(totalMs / Math.max(body.length, 1));
    }
  }

  private finished(id: string, ...kinds: string[]): MockJob {
    const j = this.jobs.get(id);
    if (!j) throw new ApiError(404, `no job ${id}`);
    if (!kinds.includes(j.job.kind)) throw new ApiError(400, `${id} is a ${j.job.kind} job`);
    if (j.job.status !== "done") throw new ApiError(409, `${id} is ${j.job.status}`);
    return j;
  }

  // --- settings and policies --------------------------------------------------------------

  async settings(): Promise<Settings> {
    return { playback: this.playback, api_key: false };
  }

  async setSettings(s: { playback: boolean }): Promise<Settings> {
    this.playback = s.playback;
    return this.settings();
  }

  async policies() {
    const synth = F.synthesize.result.policy;
    const extra = [...this.applied].map((v) => ({
      name: v,
      version: v,
      parent: synth.parent,
      controls: F.synthesize.result.chosen,
      diff: synth.diff,
    }));
    return [...clone(F.policies), ...extra];
  }

  // --- runs -------------------------------------------------------------------------------

  async reset(policy: string, operator: OperatorKind = "reference") {
    this.runs.clear();
    return this.createRun(policy, operator);
  }

  async createRun(policy: string, operator: OperatorKind = "reference") {
    const run = this.newRun({ ...F.fresh, policy, operator }, F.fresh_entities);
    return clone(run.summary);
  }

  // O1: the mock has no documents recorded; the LLM Operator needs the real backend.
  async documents(): Promise<MessyDocument[]> {
    return [];
  }

  async deliver(): Promise<DeliverOut> {
    throw new ApiError(400, "the mock has no messy documents; connect the backend for the LLM Operator");
  }

  async intake(): Promise<IntakeRead[]> {
    return [];
  }

  async state(runId: string) {
    return clone(this.run(runId).summary);
  }

  async entities(runId: string) {
    return clone(this.run(runId).entities);
  }

  async ledger(runId: string) {
    const run = this.run(runId);
    return run.summary.day === 0 ? clone(F.ledger.slice(0, 1)) : clone(F.ledger);
  }

  async chain(runId: string, payment: string): Promise<Chain> {
    const run = this.run(runId);
    const pay = run.entities.payments.find((p) => p.id === payment);
    if (!pay) throw new ApiError(404, `no payment ${payment} in ${runId}`);
    if (payment === F.chain.payment && run.summary.policy === "v0" && run.entities.labels.length) {
      return clone(F.chain); // the recorded attack's broken chain
    }
    const covered = (F.chain as Chain).links.map((l) => ({
      ...l,
      status: "covered" as const,
      gap: null,
      reason: "",
      entities: [],
      events: [],
      facts: {},
    }));
    return { payment, invoice: pay.invoice ?? "", links: covered };
  }

  async operate(runId: string, days: number) {
    const run = this.run(runId);
    return this.submit("operate", { run_id: runId, days }, async (ch) => {
      const events: unknown[] = F.events;
      const verdicts: Message[] = F.verdicts;
      const progress: Message[] = F.operate_progress.filter((m: Message) => m.event === "progress");
      const per = Math.ceil(events.length / progress.length);
      const vper = Math.ceil(verdicts.length / progress.length);
      for (let i = 0; i < progress.length; i++) {
        events.slice(i * per, (i + 1) * per).forEach((e) => run.events.publish("event", e));
        verdicts.slice(i * vper, (i + 1) * vper).forEach((m) => run.verdicts.publish(m.event, m.data));
        ch.publish("progress", progress[i].data);
        await sleep(350);
      }
      run.summary = { ...clone(F.operated), run_id: runId, policy: run.summary.policy };
      run.entities = { ...clone(F.operated_entities), run_id: runId };
      return clone(run.summary);
    });
  }

  async replay(moves: Move[], policy: string, labels: OracleLabel[] = []): Promise<ReplayOut> {
    await sleep(300);
    const known = F.policies.some((p: { name: string }) => p.name === policy) || this.applied.has(policy);
    if (!known) throw new ApiError(400, `unknown policy '${policy}'`);
    const held = policy !== "v0"; // every recorded policy past v0 holds the recorded attack
    const src = held ? F.replay_after : F.replay_before;
    const run = this.newRun(
      { ...src.run, policy },
      held ? F.after_entities : F.attacked_entities,
      held ? F.after_verdicts : F.attacked_verdicts,
    );
    run.entities.labels = [...clone(src.labels), ...labels];
    (F.events as unknown[]).forEach((e) => run.events.publish("event", e));
    return {
      run: clone(run.summary),
      result: { ...clone(src.result), moves },
      labels: run.entities.labels,
    };
  }

  // --- jobs -------------------------------------------------------------------------------

  async job<R>(id: string): Promise<Job<R>> {
    const j = this.jobs.get(id);
    if (!j) throw new ApiError(404, `no job ${id}`);
    return clone({ ...j.job, messages: j.channel.messages.length }) as Job<R>;
  }

  async search(body: SearchBody) {
    return this.submit("search", { ...body }, async (ch) => {
      await this.replayMessages(ch, F.search_progress, 1800);
      return { ...clone(F.search.result), depth: body.depth, scenario: body.scenario };
    });
  }

  async diagnose(searchId: string) {
    const j = this.finished(searchId, "search", "inject");
    if (!(j.job.result as any)?.best) return { search_id: searchId, diagnosis: null, reason: "the search found no violation" };
    await sleep(200);
    return { ...clone(F.diagnose), search_id: searchId };
  }

  async synthesize(body: SynthesizeBody) {
    this.finished(body.search_id, "search", "inject");
    return this.submit("synthesize", { ...body }, async (ch) => {
      await this.replayMessages(ch, F.synthesize_log, 4000);
      return clone(F.synthesize.result);
    });
  }

  async verify(synthesisId: string, depth: number) {
    this.finished(synthesisId, "synthesize");
    return this.submit("verify", { synthesis_id: synthesisId, depth }, async (ch) => {
      await this.replayMessages(ch, F.verify_progress, 2500);
      return clone(F.verify.result);
    });
  }

  async metrics(policies: string[], depth = 1) {
    await sleep(400);
    const all = F.metrics.scorecards;
    const scorecards: Record<string, unknown> = {};
    for (const p of policies) scorecards[p] = clone(all[p] ?? all["v1-synth"]);
    return { depth, scorecards } as any;
  }

  inject = (async (runId: string, body: InjectBody) => {
    this.run(runId);
    if (!body.moves?.length && !body.description?.trim()) throw new ApiError(400, "give a description or moves");
    if (body.dry_run) {
      await sleep(300);
      if (body.moves?.length) {
        return { plan: { description: body.description || "composed trace", moves: body.moves, labels: body.labels ?? [], scenario: body.scenario ?? "a", notes: [], source: "trace" } };
      }
      return { plan: { ...clone(F.inject_plan.plan), description: body.description } };
    }
    return this.submit("inject", { run: runId, policy: this.run(runId).summary.policy }, async (ch) => {
      ch.publish("progress", { step: "fresh clone", violated: [] });
      await sleep(800);
      ch.publish("progress", { depth: 1, explored: 24 });
      await sleep(800);
      return clone(F.inject.result);
    });
  }) as VandalApi["inject"];

  // --- Blue -------------------------------------------------------------------------------

  async approvals(): Promise<Approvals> {
    const payments = [...this.runs.values()].flatMap((r) =>
      r.entities.approval_requests
        .filter((a) => a.status === "pending")
        .map((a) => ({
          run_id: r.summary.run_id,
          id: a.id,
          invoice: a.subject,
          amount: a.instruction.amount,
          payee_account: a.instruction.payee_account,
          requested_by: a.requested_by,
        })),
    );
    return { payments, patches: clone([...this.patches.values()]) };
  }

  async decidePayment(runId: string, requestId: string, actor: Actor, approve: boolean, reason = "") {
    const run = this.run(runId);
    await sleep(150);
    if (actor.role !== "approver") {
      return { ok: false, decision: "block" as const, fired: ["sod.role.approvals.decide"], error: `${actor.id} (${actor.role}) can't decide approvals` };
    }
    run.entities.approval_requests = run.entities.approval_requests.map((a) =>
      a.id === requestId ? { ...a, status: approve ? "approved" : "denied", decided_by: actor.id, reason } : a,
    );
    return { ok: true, decision: "allow" as const, fired: [], error: null };
  }

  async submitPatch(verifyJobId: string, submittedBy: Actor) {
    this.finished(verifyJobId, "verify");
    if (!["synthesizer", "approver"].includes(submittedBy.role)) {
      throw new ApiError(403, `${submittedBy.id} (${submittedBy.role}) can't submit policy patches`);
    }
    const p: PatchRequest = { ...toPatch(clone(F.patch)), id: nextId("PATCH"), submitted_by: submittedBy.id, submitter_role: submittedBy.role };
    this.patches.set(p.id, p);
    return clone(p);
  }

  async decidePatch(patchId: string, actor: Actor, approve: boolean, reason = "") {
    const p = this.patches.get(patchId);
    if (!p) throw new ApiError(404, `no patch ${patchId}`);
    if (actor.role !== "approver") throw new ApiError(403, `${actor.id} (${actor.role}) can't decide policy patches; only an approver can`);
    if (actor.id === p.submitted_by) throw new ApiError(409, `${patchId} needs a second approver`);
    if (p.status !== "pending") throw new ApiError(409, `${patchId} is ${p.status}`);
    Object.assign(p, { status: approve ? "approved" : "denied", decided_by: actor.id, reason });
    return clone(p);
  }

  async applyPolicy(version: string) {
    const p = [...this.patches.values()].find((x) => x.version === version && x.status === "approved");
    if (!p) throw new ApiError(409, `${version} needs an approved patch in the inbox to apply`);
    p.status = "applied";
    this.applied.add(version);
    return { applied: version, patch: p.id, approved_by: p.decided_by ?? "" };
  }

  async explain(entityType: string, id: string, runId: string, question?: string) {
    this.run(runId);
    await sleep(250);
    return { ...clone(F.explain), subject: id, entity_type: entityType, question: question ?? null };
  }

  // --- streams ----------------------------------------------------------------------------

  stream(path: string, handlers: Handlers, onEnd?: () => void): () => void {
    const [clean] = path.split("?");
    const parts = clean.split("/").filter(Boolean);
    if (parts[0] === "runs") {
      const run = this.run(parts[1]);
      return (parts[2] === "verdicts" ? run.verdicts : run.events).follow(handlers, onEnd);
    }
    if (parts[0] === "jobs") {
      const j = this.jobs.get(parts[1]);
      if (!j) throw new ApiError(404, `no job ${parts[1]}`);
      return j.channel.follow(handlers, onEnd);
    }
    throw new ApiError(404, path);
  }
}
