"use client";

import { useMemo, useState } from "react";
import { attackerAccounts, cx, INVARIANTS, usd, usdShort } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { Badge, Empty, Panel, Stat, Table, Tabs, td } from "./ui";

type Tab = "invoices" | "payments" | "ledger" | "bank" | "vendors";

const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "blue" | "dim" | "esc"> = {
  paid: "ok",
  settled: "ok",
  verified: "ok",
  applied: "ok",
  approved: "blue",
  scheduled: "blue",
  submitted: "blue",
  acknowledged: "blue",
  validated: "dim",
  received: "dim",
  held: "warn",
  open: "warn",
  unverified: "warn",
  pending: "warn",
  failed: "bad",
  misdirected: "bad",
  rejected: "bad",
  recalled: "esc",
  superseded: "dim",
  cancelled: "dim",
};

function Status({ value }: { value: string }) {
  return <Badge tone={STATUS_TONE[value] ?? "dim"}>{value}</Badge>;
}

export function TwinPanel() {
  const s = useWarRoom();
  const [tab, setTab] = useState<Tab>("payments");
  const e = s.entities;
  const summary = s.summary;

  const vendorName = useMemo(() => new Map(e?.vendors.map((v) => [v.id, v.name]) ?? []), [e]);
  const accounts = useMemo(() => new Map(e?.vendor_bank_accounts.map((a) => [a.id, a]) ?? []), [e]);
  const attacker = useMemo(
    () => (e && s.judge ? attackerAccounts(e.labels, e.vendor_bank_accounts) : new Set<string>()),
    [e, s.judge],
  );
  const invoiceVendor = useMemo(() => new Map(e?.invoices.map((i) => [i.id, i.vendor]) ?? []), [e]);

  const tab_ = s.tabs.find((t) => t.id === s.focusRunId);
  const paid = summary ? (summary.invoices.paid ?? 0) : 0;
  const totalInv = summary ? Object.values(summary.invoices).reduce((a, b) => a + b, 0) : 0;
  const violated = [...new Set(summary?.violations.map((v) => v.invariant) ?? [])];

  return (
    <Panel
      title={
        <>
          Financial twin <span className="normal-case tracking-normal text-faint">· {summary?.company ?? "…"}</span>
        </>
      }
      actions={
        summary && (
          <span className="num text-[11px] text-faint" title={summary.state_hash}>
            {tab_?.kind === "replay" ? tab_.label : `Live · ${summary.policy}`} · {summary.events} events · #
            {summary.state_hash.slice(0, 8)}
          </span>
        )
      }
      bodyClass="flex flex-col"
    >
      <div className="grid shrink-0 grid-cols-2 border-b border-line sm:grid-cols-5">
        <Stat label="Cash" value={e ? usdShort(e.totals.cash) : "—"} sub={e && `${e.bank_accounts.length} accounts`} />
        <Stat label="Open AP" value={e ? usdShort(e.totals.open_ap) : "—"} sub={summary && `${summary.open_approvals} awaiting approval`} />
        <Stat
          label="Exposure"
          value={e ? usdShort(e.totals.exposure) : "—"}
          tone={e && e.totals.exposure > 0 ? "bad" : "ok"}
          sub={e && (e.totals.exposure > 0 ? "money to the wrong place" : "none")}
        />
        <Stat label="Day" value={summary?.day ?? "—"} sub={summary && `${paid}/${totalInv} invoices paid`} />
        <Stat
          label="Invariants"
          value={violated.length ? `${violated.length} broken` : "all hold"}
          tone={violated.length ? "bad" : "ok"}
          sub={
            violated.length ? (
              <span title={violated.map((v) => `${v}: ${INVARIANTS[v] ?? ""}`).join("\n")}>{violated.join(" ")}</span>
            ) : (
              "INV-1 … INV-11"
            )
          }
        />
      </div>

      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "payments", label: `Payments ${e ? e.payments.length : ""}` },
          { id: "invoices", label: `Invoices ${e ? e.invoices.length : ""}` },
          { id: "ledger", label: `Ledger ${s.ledger.length || ""}` },
          { id: "bank", label: `Bank feed ${e ? e.bank_transactions.length : ""}` },
          { id: "vendors", label: "Vendors" },
        ]}
      />

      <div className="min-h-0 flex-1 overflow-auto">
        {!e && <Empty>Loading the twin…</Empty>}

        {e && tab === "payments" && (
          <Table head={["Payment", "Invoice", "Vendor", "Amount", "Payee account", "Status", ""]}>
            {[...e.payments].reverse().map((p) => {
              const acct = p.payee_account ? accounts.get(p.payee_account) : undefined;
              const bad = p.payee_account && attacker.has(p.payee_account);
              const selected = s.chain.payment === p.id;
              return (
                <tr
                  key={p.id}
                  onClick={() => s.selectPayment(p.id)}
                  className={cx("cursor-pointer hover:bg-raised", selected && "bg-blue/10", bad && "bg-bad/10")}
                >
                  <td className={cx(td, "num")}>{p.id}</td>
                  <td className={cx(td, "num text-dim")}>{p.invoice}</td>
                  <td className={td}>{vendorName.get(invoiceVendor.get(p.invoice ?? "") ?? "") ?? ""}</td>
                  <td className={cx(td, "num text-right")}>{p.amount != null ? usd(p.amount) : ""}</td>
                  <td className={cx(td, "num")}>
                    {p.payee_account}
                    {acct && acct.status !== "verified" && (
                      <span className="ml-1">
                        <Status value={acct.status} />
                      </span>
                    )}
                    {bad && <span className="ml-1 text-[10px] font-bold text-esc">ATTACKER</span>}
                  </td>
                  <td className={td}>
                    <Status value={p.status} />
                  </td>
                  <td className={td}>
                    <button
                      onClick={(ev) => {
                        ev.stopPropagation();
                        s.explain("payment", p.id);
                      }}
                      className="text-[11px] text-blue hover:underline"
                    >
                      why?
                    </button>
                  </td>
                </tr>
              );
            })}
          </Table>
        )}

        {e && tab === "invoices" && (
          <Table head={["Invoice", "Vendor", "Number", "PO", "Amount", "Due", "Status", ""]}>
            {e.invoices.map((i) => (
              <tr key={i.id} className="hover:bg-raised">
                <td className={cx(td, "num")}>{i.id}</td>
                <td className={td}>{vendorName.get(i.vendor) ?? i.vendor}</td>
                <td className={cx(td, "num text-dim")}>{i.number}</td>
                <td className={cx(td, "num text-dim")}>{i.po ?? "—"}</td>
                <td className={cx(td, "num text-right")}>{usd(i.amount)}</td>
                <td className={cx(td, "num text-dim")}>d{i.due_date}</td>
                <td className={td}>
                  <Status value={i.status} />
                  {i.kind === "credit_memo" && <span className="ml-1 text-[10px] text-faint">credit memo</span>}
                </td>
                <td className={td}>
                  <button onClick={() => s.explain("invoice", i.id)} className="text-[11px] text-blue hover:underline">
                    why?
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}

        {e && tab === "ledger" && (
          <Table head={["Entry", "Day", "Memo", "Account", "Debit", "Credit"]}>
            {[...s.ledger].reverse().flatMap((je) =>
              je.lines.map((ln, k) => (
                <tr key={`${je.id}-${k}`} className={cx(k === 0 && "border-t border-line")}>
                  <td className={cx(td, "num text-dim")}>{k === 0 ? je.id : ""}</td>
                  <td className={cx(td, "num text-dim")}>{k === 0 ? `d${je.posted_on}` : ""}</td>
                  <td className={cx(td, "text-dim")}>
                    {k === 0 ? je.memo : ""}
                    {k === 0 && je.reverses_entry_id && <span className="ml-1 text-warn">reverses {je.reverses_entry_id}</span>}
                  </td>
                  <td className={cx(td, "num")}>{ln.account}</td>
                  <td className={cx(td, "num text-right")}>{ln.debit ? usd(ln.debit) : ""}</td>
                  <td className={cx(td, "num text-right")}>{ln.credit ? usd(ln.credit) : ""}</td>
                </tr>
              )),
            )}
          </Table>
        )}

        {e && tab === "bank" && (
          <>
            <div className="flex flex-wrap gap-4 border-b border-line px-3 py-2">
              {e.bank_accounts.map((b) => (
                <div key={b.id} className="text-xs">
                  <span className="text-dim">{b.name}</span>{" "}
                  <span className="num font-semibold">{usd(b.balance)}</span>
                </div>
              ))}
            </div>
            <Table head={["Txn", "Day", "Amount", "Payment", "Counterparty", "Memo", "Reconciled"]}>
              {[...e.bank_transactions].reverse().map((t) => (
                <tr key={t.id} className={cx(t.counterparty_account && attacker.has(t.counterparty_account) && "bg-bad/10")}>
                  <td className={cx(td, "num")}>{t.id}</td>
                  <td className={cx(td, "num text-dim")}>d{t.posted_on}</td>
                  <td className={cx(td, "num text-right", t.amount < 0 ? "text-ink" : "text-ok")}>{usd(t.amount)}</td>
                  <td className={cx(td, "num text-dim")}>{t.payment ?? t.refund ?? ""}</td>
                  <td className={cx(td, "num text-dim")}>{t.counterparty_account ?? ""}</td>
                  <td className={cx(td, "text-dim")}>{t.memo}</td>
                  <td className={td}>{t.reconciled ? <Badge tone="ok">yes</Badge> : <Badge>no</Badge>}</td>
                </tr>
              ))}
            </Table>
          </>
        )}

        {e && tab === "vendors" && (
          <div className="space-y-4 p-0">
            {e.change_requests.length > 0 && (
              <Table head={["Change request", "Vendor", "Fields", "Channel", "Sender", "Day", "Status"]}>
                {e.change_requests.map((c) => (
                  <tr key={c.id}>
                    <td className={cx(td, "num")}>
                      {c.id}{" "}
                      <button onClick={() => s.explain("change_request", c.id)} className="ml-1 text-[11px] text-blue hover:underline">
                        why?
                      </button>
                    </td>
                    <td className={td}>{vendorName.get(c.vendor) ?? c.vendor}</td>
                    <td className={td}>{c.fields}</td>
                    <td className={td}>{c.channel}</td>
                    <td className={cx(td, "num text-dim")}>{c.sender}</td>
                    <td className={cx(td, "num text-dim")}>d{c.received_on}</td>
                    <td className={td}>
                      <Status value={c.status} />
                    </td>
                  </tr>
                ))}
              </Table>
            )}
            <Table head={["Account", "Vendor", "Routing", "Account no.", "Source", "Status"]}>
              {e.vendor_bank_accounts.map((a) => (
                <tr key={a.id} className={cx(attacker.has(a.id) && "bg-bad/10")}>
                  <td className={cx(td, "num")}>
                    {a.id}
                    {attacker.has(a.id) && <span className="ml-1 text-[10px] font-bold text-esc">ATTACKER</span>}
                  </td>
                  <td className={td}>{vendorName.get(a.vendor) ?? a.vendor}</td>
                  <td className={cx(td, "num text-dim")}>{a.routing}</td>
                  <td className={cx(td, "num text-dim")}>{a.account}</td>
                  <td className={cx(td, "text-dim")}>{a.source}</td>
                  <td className={td}>
                    <Status value={a.status} />
                  </td>
                </tr>
              ))}
            </Table>
          </div>
        )}
      </div>
    </Panel>
  );
}
