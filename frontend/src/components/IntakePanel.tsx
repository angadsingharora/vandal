"use client";

import { useState } from "react";
import { usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { IntakeRead, MessyDocument } from "@/lib/types";
import { Badge, Button, Empty } from "./ui";

const FORMAT_LABEL: Record<MessyDocument["format"], string> = {
  email_body: "email body",
  ocr_text: "OCR'd scan",
  forwarded_thread: "forwarded thread",
  line_items: "line items",
};

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-dim">{label}</span>
      <span className={value == null ? "text-faint" : "num text-ink"}>{value ?? "–"}</span>
    </span>
  );
}

function ReadRow({ r }: { r: IntakeRead }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b border-line px-3 py-1.5 text-[12px] last:border-b-0">
      <span className="num text-dim">{r.message}</span>
      <Badge tone={r.intent === "invoice" || r.intent === "credit_memo" ? "blue" : r.intent === "other" ? "dim" : "warn"}>{r.intent.replace("_", " ")}</Badge>
      <Field label="vendor" value={r.vendor} />
      <Field label="no." value={r.number} />
      <Field label="amount" value={r.amount == null ? null : usd(r.amount)} />
      <Field label="PO" value={r.po} />
      <Field label="property" value={r.dimension} />
      <Field label="GL" value={r.gl_account} />
      <Badge tone={r.source === "llm" ? "esc" : "dim"}>{r.source === "llm" ? "Claude" : r.source}</Badge>
    </li>
  );
}

/** Pick one of the planted messy documents, deliver it, and watch what intake read before Blue gated the call. */
export function IntakePanel() {
  const s = useWarRoom();
  const pending = s.documents.filter((d) => !d.delivered);
  const [picked, setPicked] = useState<string>("");
  const doc = s.documents.find((d) => d.id === (picked || pending[0]?.id));
  const [open, setOpen] = useState(false);
  const busy = s.delivering === "running";

  return (
    <div className="border-b border-line">
      <div className="flex flex-wrap items-center gap-1.5 px-3 py-1.5">
        <span className="text-[12.5px] font-semibold text-ink">Intake</span>
        <select
          value={doc?.id ?? ""}
          onChange={(e) => setPicked(e.target.value)}
          disabled={pending.length === 0}
          className="h-7 min-w-0 flex-1 rounded border border-ink/20 bg-bg px-1.5 text-[12px]"
          title="A planted messy document. The answer key stays on the server."
        >
          {pending.map((d) => (
            <option key={d.id} value={d.id}>
              {d.id}, {FORMAT_LABEL[d.format]}: {d.subject}
            </option>
          ))}
          {pending.length === 0 && <option value="">Every document delivered</option>}
        </select>
        <Button tone="ghost" onClick={() => setOpen(!open)} disabled={!doc}>
          {open ? "Hide" : "Read"}
        </Button>
        <Button tone="blue" onClick={() => doc && s.deliverDocument(doc.id)} busy={busy} disabled={!doc}>
          Deliver
        </Button>
      </div>
      {open && doc && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap border-t border-line bg-raised/40 px-3 py-2 text-[12px] text-dim">
          From: {doc.sender}
          {"\n"}Subject: {doc.subject}
          {"\n\n"}
          {doc.body}
        </pre>
      )}
      {s.intake.length === 0 ? (
        <Empty>Deliver a document to see what intake reads.</Empty>
      ) : (
        <ul>
          {[...s.intake].reverse().map((r) => (
            <ReadRow key={r.message} r={r} />
          ))}
        </ul>
      )}
    </div>
  );
}
