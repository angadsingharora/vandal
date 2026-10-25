"use client";

// Evidence scan: the forensic exhibit. The attacker's actual message (the spoofed
// bank-change email, or the deepfake "confirmation" call transcript) is rendered as an
// intercepted document; a scanline sweeps it and pulls out each tell, cross-checking
// every one against the twin's own records. Nothing here is typed in: the message body
// comes from the run's channel.received event, and every verdict on the right is a
// comparison against entities the backend returned (vendor domain on file, verified
// bank account, callback evidence, the change request's fate under this policy).

import { useEffect, useMemo, useRef, useState } from "react";
import { cx, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Entities, VandalEvent } from "@/lib/types";
import { Badge, Button } from "./ui";

/** The ChannelEvent the backend dumps into a channel.received event's payload. */
interface Intercepted {
  id: string;
  day: number;
  channel: string;
  sender: string;
  subject: string;
  body: string;
  meta: Record<string, unknown>;
}

function asIntercepted(e: VandalEvent): Intercepted | null {
  const m = e.payload?.message as Record<string, unknown> | undefined;
  if (!m || typeof m.body !== "string" || typeof m.sender !== "string") return null;
  return {
    id: String(m.id ?? e.id),
    day: Number(m.day ?? e.day),
    channel: String(m.channel ?? "email"),
    sender: String(m.sender),
    subject: String(m.subject ?? ""),
    body: String(m.body),
    meta: (m.meta as Record<string, unknown>) ?? {},
  };
}

/** Positions where two equal-length strings differ (the lookalike's swapped characters). */
function diffPositions(a: string, b: string): number[] {
  if (a.length !== b.length) return [];
  const out: number[] = [];
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) out.push(i);
  return out;
}

type Tone = "bad" | "ok" | "warn" | "dim";

interface Finding {
  key: string;
  label: string;
  value: string;
  note: string;
  tone: Tone;
}

/** Everything the scan pulls, derived purely from the message + the twin's entities. */
function analyze(m: Intercepted, entities: Entities | null, policy: string) {
  const vendorId = typeof m.meta.vendor === "string" ? m.meta.vendor : null;
  const vendor = entities?.vendors.find((v) => v.id === vendorId) ?? null;
  const cr = entities?.change_requests.find((c) => c.message === m.id) ?? null;
  const proposedRouting = String(m.meta.routing ?? cr?.proposed?.routing ?? "");
  const proposedAccount = String(m.meta.account ?? cr?.proposed?.account ?? "");

  const senderDomain = m.sender.split("@")[1] ?? "";
  const realDomain = vendor?.domain ?? "";
  const domainDiff = diffPositions(senderDomain, realDomain);
  const inbound = m.channel === "phone_in" || m.channel === "video";

  const onFile = entities?.vendor_bank_accounts.find(
    (a) => a.vendor === vendorId && a.status === "verified",
  );
  const proposedVba = entities?.vendor_bank_accounts.find(
    (a) => a.routing === proposedRouting && a.account === proposedAccount,
  );
  const paid = proposedVba
    ? entities?.payments.find((p) => p.payee_account === proposedVba.id && p.amount != null)
    : undefined;

  const findings: Finding[] = [];

  if (inbound) {
    findings.push({
      key: "channel",
      label: "Channel",
      value: m.channel === "video" ? "inbound video call" : "inbound phone call",
      note: "The caller controls an inbound channel. Only an outbound callback to the number on file verifies anything.",
      tone: "bad",
    });
  } else if (senderDomain) {
    if (realDomain && domainDiff.length > 0) {
      findings.push({
        key: "sender",
        label: "Sender",
        value: m.sender,
        note: `Lookalike domain, ${domainDiff.length} character${domainDiff.length > 1 ? "s" : ""} off ${vendor?.name ?? "the vendor"}'s real domain ${realDomain}`,
        tone: "bad",
      });
    } else if (realDomain && senderDomain !== realDomain) {
      findings.push({
        key: "sender",
        label: "Sender",
        value: m.sender,
        note: `Not the vendor's domain on file, ${realDomain}`,
        tone: "bad",
      });
    } else {
      findings.push({
        key: "sender",
        label: "Sender",
        value: m.sender,
        note: "Matches the contact on file. A compromised mailbox looks identical from the text alone.",
        tone: "warn",
      });
    }
  }

  if (proposedRouting && proposedAccount) {
    findings.push({
      key: "account",
      label: "New bank details",
      value: `${proposedRouting} / ${proposedAccount}`,
      note: onFile
        ? `No payment history. Differs from the verified account on file, ending ${onFile.account.slice(-4)}.`
        : "No payment history. No verified account on file to compare.",
      tone: "bad",
    });
    findings.push({
      key: "verification",
      label: "Verification",
      value: cr && cr.evidence.length > 0 ? `${cr.evidence.length} ${cr.evidence.length === 1 ? "item" : "items"} on record` : "none",
      note:
        cr && cr.evidence.length > 0
          ? "Out-of-band evidence recorded for this change"
          : "No out-of-band callback on record for this change",
      tone: cr && cr.evidence.length > 0 ? "ok" : "bad",
    });
  }

  const contactEmail = typeof m.meta.contact_email === "string" ? m.meta.contact_email : null;
  const contactPhone = typeof m.meta.contact_phone === "string" ? m.meta.contact_phone : null;
  if (contactEmail || contactPhone) {
    findings.push({
      key: "contact",
      label: "New contact",
      value: [contactEmail, contactPhone].filter(Boolean).join(", "),
      note: "Future callbacks would reach whoever sent this message",
      tone: "bad",
    });
  }

  if (cr) {
    const applied = cr.status === "applied";
    findings.push({
      key: "fate",
      label: `Under ${policy}`,
      value: cr.status,
      note: applied
        ? "Nothing in this policy read the facts above. The change went straight onto the vendor record."
        : cr.status === "held"
          ? "The gate read the facts above and held the change for a human"
          : cr.status === "rejected"
            ? "The gate refused the change outright"
            : "Awaiting the operator",
      tone: applied ? "bad" : cr.status === "open" ? "dim" : "ok",
    });
  }

  return { vendor, cr, proposedRouting, proposedAccount, senderDomain, realDomain, domainDiff, findings, paid };
}

/** The body with the pulled values marked. Pure string splitting on real substrings. */
function MarkedBody({ body, marks, active }: { body: string; marks: { text: string; i: number }[]; active: number }) {
  const nodes: React.ReactNode[] = [];
  let rest = body;
  let k = 0;
  const found = marks
    .map((m) => ({ ...m, pos: m.text ? body.indexOf(m.text) : -1 }))
    .filter((m) => m.pos >= 0 && m.text.length > 0)
    .sort((a, b) => a.pos - b.pos);
  let cursor = 0;
  for (const m of found) {
    if (m.pos < cursor) continue;
    nodes.push(<span key={k++}>{body.slice(cursor, m.pos)}</span>);
    nodes.push(
      <mark key={k++} className={cx("es-mark num", active >= m.i && "on")}>
        {m.text}
      </mark>,
    );
    cursor = m.pos + m.text.length;
  }
  nodes.push(<span key={k++}>{body.slice(cursor)}</span>);
  void rest;
  return <>{nodes}</>;
}

function SenderLine({ sender, realDomain, diff, active }: { sender: string; realDomain: string; diff: number[]; active: boolean }) {
  const [local, domain] = [sender.split("@")[0], sender.split("@")[1] ?? ""];
  if (!active || diff.length === 0 || !domain) {
    return <span className={cx("es-mark", active && "on")}>{sender}</span>;
  }
  return (
    <span className="es-mark on">
      {local}@
      {domain.split("").map((ch, i) =>
        diff.includes(i) ? (
          <b key={i} className="es-forged" title={`The real domain has “${realDomain[i]}” here`}>
            {ch}
          </b>
        ) : (
          <span key={i}>{ch}</span>
        ),
      )}
    </span>
  );
}

const CHANNEL_LABEL: Record<string, string> = {
  email: "email",
  portal: "vendor portal",
  agent_msg: "agent message",
  phone_in: "inbound call transcript",
  video: "video call transcript",
};

/** The scanner. Renders on the Red side whenever the focused run intercepted a channel
 * message; sweeps it and pulls the tells, one cross-check at a time. */
export function EvidenceScan() {
  const s = useWarRoom();
  const policy = s.tabs.find((t) => t.id === s.focusRunId)?.policy ?? s.summary?.policy ?? "v0";

  const messages = useMemo(
    () => s.activity.filter((e) => e.kind === "channel.received").map(asIntercepted).filter((m): m is Intercepted => m !== null),
    [s.activity],
  );
  const [pickedId, setPickedId] = useState<string | null>(null);
  const msg = messages.find((m) => m.id === pickedId) ?? messages[messages.length - 1] ?? null;

  const a = useMemo(() => (msg ? analyze(msg, s.entities, policy) : null), [msg, s.entities, policy]);

  // one scan per message per focused run; Rescan replays it
  const [step, setStep] = useState(0); // 0 = idle, 1..n = findings revealed, done when > findings
  const timers = useRef<number[]>([]);
  const scanKey = msg ? `${s.focusRunId}:${msg.id}` : null;
  const lastKey = useRef<string | null>(null);

  const play = (n: number) => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setStep(n + 1);
      return;
    }
    setStep(0);
    for (let i = 1; i <= n + 1; i++) {
      timers.current.push(window.setTimeout(() => setStep(i), 350 + i * 420));
    }
  };

  useEffect(() => {
    if (!scanKey || !a) return;
    if (lastKey.current === scanKey) return;
    lastKey.current = scanKey;
    play(a.findings.length);
    return () => timers.current.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanKey, a?.findings.length]);

  if (!msg || !a) return null;

  const scanning = step <= a.findings.length;
  const judgeLabels = s.judge
    ? (s.entities?.labels ?? []).filter(
        (l) => l.subject === msg.id || (a.proposedAccount && l.subject.includes(a.proposedAccount)),
      )
    : [];
  const marks = [
    { text: a.proposedRouting, i: findingIndex(a.findings, "account") },
    { text: a.proposedAccount, i: findingIndex(a.findings, "account") },
  ].filter((m) => m.text);

  return (
    <section aria-label="Evidence scan" className="shrink-0 bg-panel">
      <div className="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-3 py-1">
        <span className="text-[12.5px] font-semibold leading-none text-ink">Evidence</span>
        <span className="text-[11px] text-dim">
          <span className="num">{msg.id}</span>, intercepted day <span className="num">{msg.day}</span>,{" "}
          {CHANNEL_LABEL[msg.channel] ?? msg.channel}
        </span>
        {messages.length > 1 && (
          <span className="flex items-center gap-2">
            {messages.map((m) => (
              <button
                key={m.id}
                onClick={() => setPickedId(m.id)}
                className={cx("num text-[11px]", m.id === msg.id ? "text-red" : "text-dim hover:text-ink")}
              >
                {m.id}
              </button>
            ))}
          </span>
        )}
        <Button tone="ghost" className="ml-auto" onClick={() => play(a.findings.length)}>
          Rescan
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        {/* the exhibit */}
        <div className="relative overflow-hidden bg-raised/40 p-3">
          {scanning && <div className="es-scanline" aria-hidden />}
          <div className="space-y-0.5 border-b border-line pb-2 text-[12px]">
            <div>
              <span className="text-dim">From </span>
              <SenderLine
                sender={msg.sender}
                realDomain={a.realDomain}
                diff={a.domainDiff}
                active={step > findingIndex(a.findings, "sender") || step > findingIndex(a.findings, "channel")}
              />
            </div>
            {msg.subject && (
              <div>
                <span className="text-dim">Subject </span>
                <span className="text-ink">{msg.subject}</span>
              </div>
            )}
          </div>
          <div className="max-h-44 overflow-auto whitespace-pre-wrap pt-2 text-[12px] leading-relaxed text-ink/80">
            <MarkedBody body={msg.body} marks={marks} active={step} />
          </div>
        </div>

        {/* what the scan pulled */}
        <div className="border-t border-line p-3 md:border-l md:border-t-0">
          <div className="mb-2 text-[11px] text-dim">Checked against the copy&apos;s own records</div>
          <ul className="space-y-1.5">
            {a.findings.map((f, i) => (
              <li
                key={f.key}
                className={cx(
                  "es-finding border-l-2 py-1 pl-2 text-[12px]",
                  step > i ? "on" : "off",
                  f.tone === "bad" && "border-red",
                  f.tone === "ok" && "border-blue",
                  f.tone === "warn" && "border-warn",
                  f.tone === "dim" && "border-line",
                )}
              >
                <div className="flex items-baseline gap-2">
                  <span className="w-24 shrink-0 text-[11px] text-dim">{f.label}</span>
                  <span
                    title={f.value}
                    className={cx("num min-w-0 flex-1 truncate", f.tone === "bad" ? "text-red" : f.tone === "ok" ? "text-blue" : "text-ink")}
                  >
                    {f.value}
                  </span>
                </div>
                <div className="text-[11px] text-dim">{f.note}</div>
              </li>
            ))}
          </ul>
          {step > a.findings.length && a.cr?.status === "applied" && (
            <div className="es-finding on mt-2 border-l-2 border-red py-1 pl-2 text-[12px] font-medium text-red">
              <span className="num">{a.paid?.amount != null ? usd(a.paid.amount) : s.attack ? usd(s.attack.finding.exposure) : "The payment"}</span>{" "}
              followed this message.
            </div>
          )}
          {step > a.findings.length && judgeLabels.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-line pt-2">
              <span className="text-[11px] text-dim">Answer key</span>
              {judgeLabels.map((l) => (
                <Badge key={l.subject + l.label} tone="esc">
                  {l.label.replace(/_/g, " ")}: {String(l.value)}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function findingIndex(findings: Finding[], key: string): number {
  const i = findings.findIndex((f) => f.key === key);
  return i === -1 ? 0 : i;
}
