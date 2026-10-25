// The demo loop as seven steps across the two sides: Blue operates, Red attacks a clone and
// builds a fix, Blue approves and enforces it. Pure, so the stepper, the pages and their
// tests agree. Each step is also a page of the war room, named by its `id`.

export type Side = "red" | "blue";

export type Stage = "operate" | "attack" | "diagnose" | "fix" | "prove" | "approve" | "enforce";

export const STAGES: Stage[] = ["operate", "attack", "diagnose", "fix", "prove", "approve", "enforce"];

export interface LoopStep {
  n: number;
  id: Stage;
  side: Side;
  label: string;
  /** What to click next when this is the current step. */
  next: string;
  done: boolean;
}

/** The slice of the store the loop reads. */
export interface LoopInput {
  operated: boolean;
  attacked: boolean;
  diagnosed: boolean;
  synthesized: boolean;
  submitted: boolean;
  applied: boolean;
  enforced: boolean;
}

export function loopSteps(x: LoopInput): LoopStep[] {
  return [
    { n: 1, id: "operate", side: "blue", label: "Operate", done: x.operated, next: "Run operations. The Operator works the books while Guard checks every action." },
    { n: 2, id: "attack", side: "red", label: "Attack", done: x.attacked, next: "Unleash Vandal. Search the sandbox for a sequence of events that breaks the books." },
    { n: 3, id: "diagnose", side: "red", label: "Diagnose", done: x.diagnosed, next: "Diagnose. Find the broken link in the authorization chain." },
    { n: 4, id: "fix", side: "red", label: "Fix", done: x.synthesized, next: "Synthesize a control that closes the gap." },
    { n: 5, id: "prove", side: "red", label: "Prove", done: x.submitted, next: "Verify the control, then send it to Blue for approval." },
    { n: 6, id: "approve", side: "blue", label: "Approve", done: x.applied, next: "Approve the fix as the Controller, then apply it to Guard." },
    { n: 7, id: "enforce", side: "blue", label: "Enforce", done: x.enforced, next: "Replay Red's attack against the new policy. Guard should hold it." },
  ];
}

/** The step after the furthest one done, so skipping Operate doesn't pin the loop at step 1.
 * Null once every step is done. */
export function currentStep(steps: LoopStep[]): LoopStep | null {
  let last = -1;
  steps.forEach((s, i) => s.done && (last = i));
  return steps[last + 1] ?? null;
}

export function stepOf(steps: LoopStep[], id: Stage): LoopStep {
  return steps.find((s) => s.id === id)!;
}

export function sideOf(stage: Stage): Side {
  return stage === "operate" || stage === "approve" || stage === "enforce" ? "blue" : "red";
}

/** The page to open when someone switches to a side: the current step if it lives there,
 * else the furthest step done on that side, else the side's first page. */
export function landingStage(steps: LoopStep[], side: Side): Stage {
  const now = currentStep(steps);
  if (now && now.side === side) return now.id;
  const mine = steps.filter((s) => s.side === side);
  return (mine.filter((s) => s.done).at(-1) ?? mine[0]).id;
}
