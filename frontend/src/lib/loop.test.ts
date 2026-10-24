import assert from "node:assert/strict";
import { test } from "node:test";
import { currentStep, loopSteps, type LoopInput } from "./loop.ts";

const none: LoopInput = {
  operated: false,
  attacked: false,
  diagnosed: false,
  synthesized: false,
  submitted: false,
  applied: false,
  enforced: false,
};

test("the loop starts on Blue's Operate", () => {
  const step = currentStep(loopSteps(none));
  assert.equal(step?.label, "Operate");
  assert.equal(step?.side, "blue");
});

test("the current step follows the furthest one done, even when Operate was skipped", () => {
  assert.equal(currentStep(loopSteps({ ...none, attacked: true }))?.label, "Diagnose");
  assert.equal(currentStep(loopSteps({ ...none, operated: true, attacked: true, diagnosed: true, synthesized: true, submitted: true }))?.side, "blue");
});

test("a finished loop has no current step", () => {
  const all = Object.fromEntries(Object.keys(none).map((k) => [k, true])) as unknown as LoopInput;
  assert.equal(currentStep(loopSteps(all)), null);
});
