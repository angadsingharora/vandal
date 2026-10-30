"use client";

// The workspace's settings: which company a run is seeded from (a built-in, or one derived
// here), the run itself, and how each of Strike's jobs is asked for. Saving applies the knobs
// to the next job; "Save and start a new run" also seeds a fresh company from them.

import { useEffect, useState } from "react";
import { cx, usd } from "@/lib/format";
import { useWarRoom, type Workspace } from "@/lib/store";
import type { AttackerCapabilities, NewProfile, ProfileInfo } from "@/lib/types";
import { Button, Modal, Spinner } from "./ui";

const field = "num h-8 w-full rounded border border-line bg-bg px-2 text-xs";
const label = "flex flex-col gap-1 text-[11px] text-dim";

function Section({ title, blurb, children }: { title: string; blurb?: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-line pt-4 first:border-t-0 first:pt-0">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-ink">{title}</h3>
      {blurb && <p className="mt-0.5 text-[11px] leading-snug text-faint">{blurb}</p>}
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
    </section>
  );
}

function Num({ id, text, value, onChange, min, max, step, title }: { id: string; text: string; value: number; onChange: (n: number) => void; min?: number; max?: number; step?: number; title?: string }) {
  return (
    <label htmlFor={id} className={label} title={title}>
      {text}
      <input id={id} type="number" value={value} min={min} max={max} step={step} onChange={(e) => onChange(Number(e.target.value))} className={field} />
    </label>
  );
}

function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-dim">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="accent-blue" />
      {children}
    </label>
  );
}

const CHANNELS: { id: string; text: string }[] = [
  { id: "email", text: "email" },
  { id: "agent_msg", text: "message to the agent" },
  { id: "portal", text: "vendor portal (needs takeover)" },
];
const SENDERS: { id: string; text: string }[] = [
  { id: "lookalike", text: "lookalike domain" },
  { id: "compromised_mailbox", text: "compromised mailbox" },
];
const ABILITIES: { id: keyof Omit<AttackerCapabilities, "change_request_channels" | "senders">; text: string }[] = [
  { id: "spoof_caller_id", text: "spoof caller ID" },
  { id: "clone_voice", text: "clone a voice" },
  { id: "portal_takeover", text: "take over the vendor portal" },
  { id: "submit_invoices", text: "submit invoices" },
  { id: "deposits", text: "send deposits (money in)" },
];

/** The custom-company form, prefilled from a base profile. Money is entered in dollars. */
function CustomCompany({ base, onMade }: { base: ProfileInfo; onMade: (p: ProfileInfo) => void }) {
  const s = useWarRoom();
  const [name, setName] = useState("");
  const [threshold, setThreshold] = useState(base.approval.threshold / 100);
  const [tolerance, setTolerance] = useState(base.approval.match_tolerance_pct);
  const [priors, setPriors] = useState(base.approval.min_prior_payments);
  const [window, setWindow] = useState(base.approval.aggregate_window_days);
  const [invoices, setInvoices] = useState(base.generation.invoices);
  const [pending, setPending] = useState(base.generation.pending_invoices);
  const [history, setHistory] = useState(base.generation.history_days);
  const [horizon, setHorizon] = useState(base.operator.payment_horizon_days);
  const [blocked, setBlocked] = useState(base.risk.lambda_per_blocked / 100);
  const [hold, setHold] = useState(base.risk.mu_per_hold / 100);
  const [attacker, setAttacker] = useState<AttackerCapabilities>(base.attacker);
  const [busy, setBusy] = useState(false);

  const toggleIn = (key: "change_request_channels" | "senders", id: string) =>
    setAttacker((a) => ({ ...a, [key]: a[key].includes(id) ? a[key].filter((x) => x !== id) : [...a[key], id] }));

  const create = async () => {
    setBusy(true);
    const body: NewProfile = {
      base: base.name,
      company_name: name.trim() || undefined,
      approval: { threshold: Math.round(threshold * 100), match_tolerance_pct: tolerance, min_prior_payments: priors, aggregate_window_days: window },
      generation: { invoices, pending_invoices: pending, history_days: history },
      attacker,
      risk: { lambda_per_blocked: Math.round(blocked * 100), mu_per_hold: Math.round(hold * 100) },
      operator: { payment_horizon_days: horizon },
    };
    const made = await s.createProfile(body);
    setBusy(false);
    if (made) onMade(made);
  };

  return (
    <div className="mt-3 space-y-4 rounded border border-line bg-raised/40 p-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label htmlFor="ws-company" className={cx(label, "sm:col-span-2")}>
          Company name
          <input id="ws-company" value={name} onChange={(e) => setName(e.target.value)} placeholder={`e.g. Harbor Dental Group (based on ${base.company})`} className={cx(field, "num-0")} />
        </label>
        <Num id="ws-threshold" text="Approval threshold ($)" value={threshold} onChange={setThreshold} min={0} step={500} title="Payments above this need a human approval" />
        <Num id="ws-tolerance" text="Match tolerance (%)" value={tolerance} onChange={setTolerance} min={0} max={50} title="How far an invoice may differ from its PO and receipt" />
        <Num id="ws-priors" text="Prior payments to trust a vendor" value={priors} onChange={setPriors} min={0} max={20} />
        <Num id="ws-window" text="Aggregate window (days)" value={window} onChange={setWindow} min={1} max={30} title="Per-vendor totals inside this window count toward the threshold" />
        <Num id="ws-invoices" text="Invoices to generate" value={invoices} onChange={setInvoices} min={1} max={400} />
        <Num id="ws-pending" text="Unpaid at day 0" value={pending} onChange={setPending} min={1} max={400} title={`At least ${base.fixtures}: the base company's planted invoices`} />
        <Num id="ws-history" text="History (days)" value={history} onChange={setHistory} min={10} max={365} />
        <Num id="ws-horizon" text="Payment horizon (days)" value={horizon} onChange={setHorizon} min={1} max={60} title="The batch pays approved invoices due within this window" />
        <Num id="ws-blocked" text="Cost per blocked legit payment ($)" value={blocked} onChange={setBlocked} min={0} step={100} title="How much the synthesizer dislikes blocking a legitimate payment" />
        <Num id="ws-hold" text="Cost per hold ($)" value={hold} onChange={setHold} min={0} step={10} title="How much the synthesizer dislikes a hold" />
      </div>
      <div>
        <div className="text-[11px] text-dim">What the attacker can do</div>
        <div className="mt-1.5 grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
          {ABILITIES.map((a) => (
            <Check key={a.id} checked={attacker[a.id]} onChange={(v) => setAttacker((x) => ({ ...x, [a.id]: v }))}>
              {a.text}
            </Check>
          ))}
        </div>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <div>
            <div className="text-[11px] text-dim">Change requests arrive by</div>
            <div className="mt-1 space-y-1">
              {CHANNELS.map((c) => (
                <Check key={c.id} checked={attacker.change_request_channels.includes(c.id)} onChange={() => toggleIn("change_request_channels", c.id)}>
                  {c.text}
                </Check>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-dim">Sent from</div>
            <div className="mt-1 space-y-1">
              {SENDERS.map((c) => (
                <Check key={c.id} checked={attacker.senders.includes(c.id)} onChange={() => toggleIn("senders", c.id)}>
                  {c.text}
                </Check>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button tone="blue" onClick={create} busy={busy}>
          Create company
        </Button>
        <span className="text-[11px] text-faint">Seeded once on the server to check it works; then it can be picked above.</span>
      </div>
    </div>
  );
}

export function WorkspaceDialog({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const [ws, setWs] = useState<Workspace>(s.ws);
  const [scenario, setScenario] = useState(s.search.scenario);
  const [searchDepth, setSearchDepth] = useState(s.search.depth);
  const [synthDepth, setSynthDepth] = useState(s.synth.depth);
  const [askClaude, setAskClaude] = useState(!s.synth.noLlm);
  const [custom, setCustom] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!s.profiles.length) void s.loadProfiles();
  }, []); // once, when the dialog opens

  const limits = s.settings?.limits;
  const maxDepth = limits?.max_depth ?? 6;
  const maxWorkers = limits?.max_workers ?? 32;
  const depths = [1, 2, 3, 4, 5, 6].filter((d) => d <= maxDepth);
  const scenarios = s.settings?.scenarios ?? {};
  const claudeAvailable = !!(s.settings?.api_key || s.settings?.playback);
  const picked = s.profiles.find((p) => p.name === ws.profile) ?? s.profiles[0];
  const policies = s.policies.map((p) => p.name);
  const set = (p: Partial<Workspace>) => setWs((w) => ({ ...w, ...p }));

  const save = () => {
    s.setWorkspace(ws);
    s.setSearch({ depth: searchDepth, scenario });
    s.setSynthDepth(synthDepth);
    s.setNoLlm(!askClaude);
  };

  const saveAndStart = async () => {
    save();
    setStarting(true);
    try {
      await s.startRun();
    } finally {
      setStarting(false);
    }
    onClose();
  };

  return (
    <Modal title="Workspace settings" onClose={onClose} wide>
      <div className="space-y-5">
        <Section title="Company" blurb="The books a run is seeded from. A custom company starts from a built-in and turns a few knobs; it lives on the server as long as it runs.">
          <label htmlFor="ws-profile" className={cx(label, "sm:col-span-2")}>
            Profile
            {s.profiles.length ? (
              <select id="ws-profile" value={picked?.name ?? ""} onChange={(e) => set({ profile: e.target.value })} className={field}>
                {s.profiles.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.company} ({p.name}{p.custom ? ", custom" : ""})
                  </option>
                ))}
              </select>
            ) : (
              <span className="flex h-8 items-center gap-2 text-xs text-faint">
                <Spinner /> loading…
              </span>
            )}
          </label>
          {picked && (
            <p className="text-[11px] leading-snug text-dim sm:col-span-2">
              {picked.vendors} vendors, {picked.generation.invoices} invoices ({picked.generation.pending_invoices} unpaid at day 0), approval above{" "}
              <span className="num text-ink">{usd(picked.approval.threshold, { cents: false })}</span>, {picked.approval.min_prior_payments} prior payments to trust a vendor.
              Attacker: {[...picked.attacker.change_request_channels, ...ABILITIES.filter((a) => picked.attacker[a.id]).map((a) => a.id.replaceAll("_", " "))].join(", ")}.
            </p>
          )}
          <div className="sm:col-span-2 lg:col-span-4">
            {s.profilesStale ? (
              <p className="text-[11px] leading-snug text-warn">
                This API is an older build without custom companies: only the built-in one is available until the host redeploys from main.
              </p>
            ) : (
              <Check checked={custom} onChange={setCustom}>
                Describe a custom company{picked ? ` based on ${picked.company}` : ""}
              </Check>
            )}
            {custom && !s.profilesStale && picked && (
              <CustomCompany
                key={picked.name}
                base={picked}
                onMade={(p) => {
                  set({ profile: p.name });
                  setCustom(false);
                }}
              />
            )}
          </div>
        </Section>

        <Section title="Run">
          <Num id="ws-seed" text="Seed" value={ws.seed} onChange={(n) => set({ seed: n })} min={0} title="Same company and seed: the same books, every time" />
          <label htmlFor="ws-policy" className={label}>
            Starting policy
            <select id="ws-policy" value={ws.policy} onChange={(e) => set({ policy: e.target.value })} className={field}>
              {policies.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <Num id="ws-days" text="Business days per operate" value={ws.operateDays} onChange={(n) => set({ operateDays: Math.max(1, Math.min(30, n || 1)) })} min={1} max={30} />
        </Section>

        <Section title="Strike" blurb="How Vandal attacks a clone of the books.">
          <label htmlFor="ws-scenario" className={cx(label, "sm:col-span-2")}>
            Threat family
            <select id="ws-scenario" value={scenario} onChange={(e) => setScenario(e.target.value)} className={field}>
              <option value="all">every family, one strike</option>
              {Object.entries(scenarios).map(([name, text]) => (
                <option key={name} value={name}>
                  {name}: {text}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="ws-depth" className={label}>
            Moves per sequence
            <select id="ws-depth" value={searchDepth} onChange={(e) => setSearchDepth(Number(e.target.value))} className={field}>
              {depths.map((d) => (
                <option key={d} value={d}>
                  k={d}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="ws-workers" className={label} title={`Parallel runs; blank uses the host's default (${limits?.default_workers ?? "auto"}), at most ${maxWorkers}`}>
            Workers
            <input
              id="ws-workers"
              type="number"
              min={1}
              max={maxWorkers}
              value={ws.workers ?? ""}
              placeholder={String(limits?.default_workers ?? "host default")}
              onChange={(e) => set({ workers: e.target.value === "" ? null : Math.max(1, Math.min(maxWorkers, Number(e.target.value))) })}
              className={field}
            />
          </label>
          <div className="sm:col-span-2 lg:col-span-4">
            <Check checked={ws.exhaustive} onChange={(v) => set({ exhaustive: v })}>
              Exhaustive: keep searching after the first sequence that breaks the books
            </Check>
          </div>
        </Section>

        <Section title="Fix and prove" blurb="Counterexample-guided synthesis, then the evidence pack.">
          <label htmlFor="ws-synth-depth" className={label}>
            Synthesis depth
            <select id="ws-synth-depth" value={synthDepth} onChange={(e) => setSynthDepth(Number(e.target.value))} className={field}>
              {depths.map((d) => (
                <option key={d} value={d}>
                  k={d}
                </option>
              ))}
            </select>
          </label>
          <Num id="ws-iterations" text="Rounds before giving up" value={ws.maxIterations} onChange={(n) => set({ maxIterations: Math.max(1, Math.min(8, n || 1)) })} min={1} max={8} />
          <label htmlFor="ws-verify-depth" className={label}>
            Verification depth
            <select id="ws-verify-depth" value={ws.verifyDepth ?? ""} onChange={(e) => set({ verifyDepth: e.target.value === "" ? null : Number(e.target.value) })} className={field}>
              <option value="">same as synthesis</option>
              {depths.map((d) => (
                <option key={d} value={d}>
                  k={d}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end pb-2">
            <Check checked={askClaude && claudeAvailable} onChange={setAskClaude}>
              Ask Claude for candidates{claudeAvailable ? "" : " (no key: sweeping templates)"}
            </Check>
          </div>
        </Section>
      </div>

      <footer className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-4">
        <span className="min-w-0 flex-1 text-[11px] text-faint">Saved settings apply to the next job. A new run replaces the current runs on the server.</span>
        <Button
          onClick={() => {
            save();
            onClose();
          }}
        >
          Save
        </Button>
        <Button tone="blue" onClick={saveAndStart} busy={starting} disabled={!s.ready}>
          Save and start a new run
        </Button>
      </footer>
    </Modal>
  );
}
