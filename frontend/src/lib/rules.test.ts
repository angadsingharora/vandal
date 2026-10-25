import assert from "node:assert/strict";
import { test } from "node:test";
import { readRule } from "./rules.ts";

test("T2 reads as the approved instruction binding", () => {
  const r = readRule({ template: "T2", params: { bound_fields: ["amount", "payee_account"], on_mismatch: "hold" } });
  assert.equal(r.name, "Approval binding");
  assert.equal(r.does.length, 1);
  assert.match(r.does[0], /the amount and the payee account/);
  assert.match(r.does[0], /holds it for a human/);
});

test("T1 names the channel, the contact as of before the request, and the window", () => {
  const r = readRule({ template: "T1", params: { accepted_channels: ["phone_outbound"], contact_as_of: "before_request", window_days: 30 } });
  assert.equal(r.does.length, 3);
  assert.match(r.does[0], /outbound phone call to the number on file/);
  assert.match(r.does[0], /before the request arrived/);
  assert.match(r.does[0], /last 30 days/);
});

test("T5 shows the threshold in dollars", () => {
  const r = readRule({ template: "T5", params: { group_by: "vendor", window_days: 5, threshold: 2500000 } });
  assert.match(r.does[0], /\$25,000/);
});

test("an unknown template still lists its parameters", () => {
  const r = readRule({ template: "T9", params: { x: 1 } });
  assert.deepEqual(r.does, ["x: 1"]);
});
