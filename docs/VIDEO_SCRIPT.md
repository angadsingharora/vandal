# Vandal: Demo Video Script

**Break it. Fix it. Prove it.**

A 2:45 shooting script for four speakers, about 370 spoken words over one continuous screen recording. It opens on the moment, as the Hyphenate brief asks, then walks the war room's seven steps in the order the product runs them. Every number in it is one the app shows.

## Cast

| Speaker | Part | Time |
|---|---|---|
| **Angad** | Cold open, the problem, the close | ~0:55 |
| **Mohith** | The Operator and Guard, then approval and replay | ~0:45 |
| **Dhruv** | Vandal Strike and Claude's threat hunter | ~0:35 |
| **Kashish** | Diagnose and Fix | ~0:30 |

Names are matched to who built each part. Swap freely.

## Script

### 0:00 – 0:12 · Cold open · Angad
> **On screen:** Attack page, red banner: "THE BOOKS BALANCE. $40,000.00 WENT TO THE WRONG ACCOUNT." Slow push in.

Every check passed. The invoice was real. The boss approved it. The books balance. **And forty thousand dollars just went to a scammer.**

### 0:12 – 0:32 · The problem · Angad
> **On screen:** Landing page: the VANDAL title and the seven-step loop.

Companies are handing their bills to AI agents. Attackers noticed. They spoof vendors, clone voices, and send in their own AI. The controls these companies rely on were built for human clerks. **We're Vandal: a red team and a blue team for the AI that runs your money.**

### 0:32 – 0:57 · 1 · Operate · Mohith
> **On screen:** Operate page. Click Run operations. The Guard verdict feed fills: 145 checked, 144 allowed, 1 escalated.

Meet Bayline, a property manager with twenty-five contractors and two million dollars in the bank. Our Operator, built on Claude, does the accounts-payable job: it reads messy invoices, codes them, gets approvals, and pays. But it never touches money directly. **Every action goes through Guard**, which checks it against independent records and allows, holds, or escalates. A hundred and forty-five actions, every one checked.

### 0:57 – 1:32 · 2 · Attack · Dhruv
> **On screen:** Attack page. Release Vandal Strike: the counter runs, the sequence appears. Then the Hunt panel: Claude's attempt, "broke INV-3 · $40,000 · outside the preset search."

Then we release Vandal Strike. Strike clones the company and attacks the copy, never the live books. It tries every short sequence of attacker moves and bank glitches, and in under a second it finds one: a fake bank-change email that lands after approval. Every step looks legit. Then we hand the attack to Claude. **It reads Bayline's books, studies Guard's rules, and invents attacks nobody wrote down.** Against rules we thought were fully fixed, it found a forty-thousand-dollar bill that gets paid twice. First try.

### 1:32 – 2:02 · 3 · Diagnose · 4 · Fix · Kashish
> **On screen:** Diagnose page: the five-link chain with Execution in red. Then Fix: candidates streaming, one rejected, the survivor T2 + T1 highlighted.

Finding the hole is half the job. Vandal walks the payment's chain, from the bill to the books, and names the broken link: the payment never checked it matched what was approved. Then it writes the fix. It proposes a rule, **attacks its own rule**, and learns from every attack that gets through. A rule a deepfake could beat gets thrown out automatically. The survivor passes six checks, including attacks it has never seen.

### 2:02 – 2:20 · 5–7 · Prove · Approve · Enforce · Mohith
> **On screen:** Approvals inbox: Approve as Controller. Enforce page: Replay. "HELD · $0.00".

A human controller signs off. Nothing goes live without that. Guard starts enforcing it, and we replay the exact same attack. **Held. Zero dollars.** And every legitimate payment still goes through.

### 2:20 – 2:45 · Close · Angad
> **On screen:** Before and after side by side: v0 $40,000 lost, v1 held $0. End on the VANDAL wordmark.

Every company putting an AI agent near its money needs two things: something that finds the gaps before attackers do, and a guard that enforces the fix on every move. **We don't patch the model. We patch the controls around it, and we prove the patch works.** We're Vandal. Break it. Fix it. Prove it.

## Recording

1. **Record the screen first, voices second.** Click through the whole loop once on a fresh Reset demo, then record each speaker's lines over it.
2. **Turn on Playback.** The recorded Claude answers make the hunt and fix steps instant and identical every take.
3. **Cut the waiting.** Speed up search and synthesis 2–4x in the edit. Never show a spinner for more than a second.
4. **Zoom on the number.** When the $40,000 banner, "outside the preset search" and the held replay appear, crop in so they fill the frame.
5. **Open on the moment.** The first frame is the red $40,000 banner, not the logo.
6. **Say only what's on screen.** If a take shows a different number or label, change the line to match the screen.

## Lines to have ready at the table

| If a judge asks | Say |
|---|---|
| Which seats would it fill? | AP specialist, vendor-master clerk, treasury and payments, cash application, staff accountant. Guard is the internal-controls reviewer. Both report to the controller. |
| What's real and what's simulated? | The ledger, the rules, the search and the fixes are real code, and Claude really reads and decides. The company, the money and the banks are simulated, scored against a hidden answer key no agent can read. |
| Is it proven secure? | No, and we don't claim that. No attack of up to k steps, within the moves we model, gets through. That's a claim a controller can sign off on. |
| Try our scenario. | Open "Try your own scenario," type the threat in plain English, and run it live. This needs the API key on the demo laptop. |
| Why was this held? | Click "why?" on the payment. Guard answers with citations, and arguing with it never clears the hold. |
