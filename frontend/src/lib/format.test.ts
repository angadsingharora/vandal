import assert from "node:assert/strict";
import { test } from "node:test";
import { atLabel, attackerAccounts, moveLine, parseParams, usd, usdShort } from "./format.ts";

test("usd formats integer cents without float drift", () => {
  assert.equal(usd(4_000_000), "$40,000.00");
  assert.equal(usd(-123_456_789), "-$1,234,567.89");
  assert.equal(usd(5), "$0.05");
  assert.equal(usd(4_000_000, { cents: false }), "$40,000");
});

test("usdShort compacts for KPI tiles", () => {
  assert.equal(usdShort(4_000_000), "$40k");
  assert.equal(usdShort(123_456_789), "$1.23M");
  assert.equal(usdShort(99_900), "$999");
});

test("atLabel follows the World's five steps a day", () => {
  assert.equal(atLabel(2), "day 0, before batch");
  assert.equal(atLabel(7), "day 1, before batch");
});

test("moveLine leaves out content text", () => {
  assert.equal(
    moveLine({ kind: "message", at: 2, params: { poses_as: "CFO", text: "It's the CFO…" } }),
    "message poses_as=CFO",
  );
});

test("parseParams keeps integers as numbers and rejects junk", () => {
  assert.deepEqual(parseParams(" vendor=V-007  amount=500000 "), { vendor: "V-007", amount: 500000 });
  assert.deepEqual(parseParams(""), {});
  assert.throws(() => parseParams("vendor"), /key=value/);
});

test("attackerAccounts maps oracle labels onto bank account ids", () => {
  const accounts = [
    { id: "BA-0001", vendor: "V-007", routing: "111", account: "222", status: "verified" as const, source: "seed", verified_by: null, verified_on: null },
    { id: "BA-0032", vendor: "V-007", routing: "026000847", account: "9680804765", status: "unverified" as const, source: "email", verified_by: null, verified_on: null },
  ];
  const labels = [
    { subject: "acct:026000847:9680804765", label: "attacker_controlled" as const, value: true },
    { subject: "MSG-0001", label: "true_sender" as const, value: "attacker" },
  ];
  assert.deepEqual([...attackerAccounts(labels, accounts)], ["BA-0032"]);
});
