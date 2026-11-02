"use client";

// Guard as an API, from the workspace: pick a tool the finance agent could call, give its
// arguments, and see what Guard would say on this run's books right now. Nothing is executed
// and nothing is recorded; the same call is POST /runs/{id}/guard/check for an integration.

import { useEffect, useMemo, useState } from "react";
import { cx } from "@/lib/format";
import { needs } from "@/lib/rules";
import { CFO, CONTROLLER, OPERATOR, useWarRoom } from "@/lib/store";
import type { Actor, GuardCheckOut, GuardTool } from "@/lib/types";
import { Button, DecisionBadge, Modal, Spinner } from "./ui";

const field = "num w-full rounded border border-line bg-bg px-2 text-xs";
const label = "flex flex-col gap-1 text-[11px] text-dim";

/** A starting value for each argument, from the run's own books where one exists. */
function example(tool: GuardTool, ids: { invoice?: string; payment?: string; vendor?: string; change?: string; request?: string }): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const a of tool.args) {
    if (!a.required && a.default !== undefined) continue;
    switch (a.name) {
      case "invoice":
        out[a.name] = ids.invoice ?? "INV-1042";
        break;
      case "payment":
        out[a.name] = ids.payment ?? "PAY-0001";
        break;
      case "vendor":
        out[a.name] = ids.vendor ?? "V-007";
        break;
      case "change":
        out[a.name] = ids.change ?? "CR-0001";
        break;
      case "request":
        out[a.name] = ids.request ?? "APR-0001";
        break;
      case "channel":
        out[a.name] = "email";
        break;
      case "sender":
        out[a.name] = "billing@vendor-example.com";
        break;
      case "fields":
        out[a.name] = "bank";
        break;
      case "contact_as_of":
        out[a.name] = "before_request";
        break;
      case "approve":
        out[a.name] = true;
        break;
      case "pay_on":
        out[a.name] = 1;
        break;
      default:
        out[a.name] = a.type.includes("int") ? 0 : a.type.includes("bool") ? false : "";
    }
  }
  return out;
}

const ACTORS: { actor: Actor; text: string }[] = [
  { actor: OPERATOR, text: "the finance agent (OP-1)" },
  { actor: CONTROLLER, text: "the Controller (U-CTRL)" },
  { actor: CFO, text: "the CFO (U-CFO)" },
];

export function AskGuardDialog({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const runId = s.focusRunId ?? s.liveRunId;
  const [tools, setTools] = useState<GuardTool[] | null>(null);
  const [tool, setTool] = useState("vendors.change_request");
  const [actor, setActor] = useState(0);
  const [args, setArgs] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [out, setOut] = useState<GuardCheckOut | null>(null);

  const ids = useMemo(() => {
    const e = s.entities;
    const open = e?.invoices.find((i) => i.status !== "paid");
    const pending = e?.change_requests.find((c) => c.status === "open" || c.status === "held");
    return {
      invoice: open?.id,
      payment: e?.payments.at(-1)?.id,
      vendor: e?.vendors[0]?.id,
      change: pending?.id ?? e?.change_requests.at(-1)?.id,
      request: e?.approval_requests.find((r) => r.status === "pending")?.id,
    };
  }, [s.entities]);

  useEffect(() => {
    let alive = true;
    s.api
      ?.guardTools()
      .then((t) => {
        if (!alive) return;
        setTools(t);
        const first = t.find((x) => x.tool === "vendors.change_request") ?? t[0];
        if (first) {
          setTool(first.tool);
          setArgs(JSON.stringify(example(first, ids), null, 2));
        }
      })
      .catch((err) => alive && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      alive = false;
    };
    // once: the ids are read when the dialog opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.api]);

  const picked = tools?.find((t) => t.tool === tool);

  const pick = (name: string) => {
    setTool(name);
    setOut(null);
    const t = tools?.find((x) => x.tool === name);
    if (t) setArgs(JSON.stringify(example(t, ids), null, 2));
  };

  const check = async () => {
    if (!runId || !s.api) return;
    setError(null);
    setOut(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(args) as Record<string, unknown>;
    } catch {
      setError("The arguments must be a JSON object.");
      return;
    }
    setBusy(true);
    try {
      setOut(await s.api.guardCheck(runId, { tool, args: parsed, actor: ACTORS[actor].actor }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Ask Guard" onClose={onClose}>
      <p className="text-xs leading-relaxed text-dim">
        What would Guard say to this tool call on the books right now, under <span className="num text-ink">{s.summary?.policy ?? "v0"}</span>? Nothing is
        executed and nothing is recorded. An integration makes the same call: <span className="num">POST /runs/{"{id}"}/guard/check</span>.
      </p>

      {!tools && !error && (
        <p className="mt-4 flex items-center gap-2 text-xs text-faint">
          <Spinner /> loading the tools…
        </p>
      )}

      {tools && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label htmlFor="ask-tool" className={label}>
            Tool
            <select id="ask-tool" value={tool} onChange={(e) => pick(e.target.value)} className={cx(field, "h-8")}>
              {tools.map((t) => (
                <option key={t.tool} value={t.tool}>
                  {t.tool}
                </option>
              ))}
            </select>
            {picked && (
              <span className="text-[11px] leading-snug text-faint">
                stage <span className="num text-dim">{picked.stage}</span>: {picked.stage_help}
              </span>
            )}
          </label>
          <label htmlFor="ask-actor" className={label}>
            Who is calling
            <select id="ask-actor" value={actor} onChange={(e) => setActor(Number(e.target.value))} className={cx(field, "h-8")}>
              {ACTORS.map((a, i) => (
                <option key={a.actor.id} value={i}>
                  {a.text}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="ask-args" className={cx(label, "sm:col-span-2")}>
            Arguments
            <textarea id="ask-args" value={args} onChange={(e) => setArgs(e.target.value)} rows={8} spellCheck={false} className={cx(field, "py-1.5 leading-relaxed")} />
            {picked && (
              <span className="text-[11px] leading-snug text-faint">
                {picked.args.map((a) => `${a.name}${a.required ? "" : "?"}: ${a.type}`).join(" · ")}
              </span>
            )}
          </label>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 text-xs text-bad">
          {error}
        </p>
      )}

      {out && (
        <div className={cx("mt-4 rounded border p-3", out.decision === "allow" ? "border-ok/40 bg-ok/[0.06]" : "border-warn/40 bg-warn/[0.06]")}>
          <div className="flex items-center gap-2">
            <DecisionBadge decision={out.decision} />
            <span className="text-sm text-ink">{out.summary}</span>
          </div>
          {out.fired.length > 0 && <div className="num mt-2 text-[11px] text-warn">fired {out.fired.join(", ")}</div>}
          {out.requires.map((r) => (
            <div key={r.check} className="mt-1 text-[11px] text-dim">
              {needs(r)}
            </div>
          ))}
          {out.missing_facts.length > 0 && <div className="num mt-1 text-[11px] text-bad">facts Guard could not compute: {out.missing_facts.join(", ")}</div>}
          {out.cites.length > 0 && <div className="num mt-2 text-[10px] text-faint">cites {out.cites.join(" ")}</div>}
        </div>
      )}

      <footer className="mt-5 flex items-center gap-3 border-t border-line pt-4">
        <span className="min-w-0 flex-1 text-[11px] text-faint">
          Day <span className="num">{s.summary?.day ?? 0}</span> of the run; the books as they are now.
        </span>
        <Button onClick={onClose}>Close</Button>
        <Button tone="blue" onClick={check} busy={busy} disabled={!tools || !runId}>
          Check
        </Button>
      </footer>
    </Modal>
  );
}
