# Conductor — 5-minute demo video script

Target: 4:30. Slides + screen recording + voiceover, no face needed. The one
non-negotiable beat is the caught lie, live, on real git. Lead with it.

Recording note: use the deterministic run so nothing depends on a model quota.
`python real_demo.py` for the terminal proof; `python serve.py` →
http://127.0.0.1:7616 for the UI. Drive the app with "Run six".

---

## 0:00–0:35 — The problem, through one person (Impact)

VISUAL: the landing hero, then cut to a plain slide with Maya's six tasks, three
turning red.

VO: "This is Maya. She's a staff engineer. This morning she handed six tasks to
her coding agents. By lunch, all six came back marked done. Three of them were
wrong. Not broken-obviously wrong — confidently, plausibly wrong. A slugify that
forgot to lowercase. A migration that passed its own script but not the schema.
Agents don't get tired. They get confidently lost, and they never tell you. So
Maya spends her afternoon reading agent output to find out which 'done' is a
lie. Every tool she has records all six as success."

## 0:35–1:05 — The thesis (Originality)

VISUAL: one line on screen: **"Done is a claim, not a fact."**

VO: "Conductor is built on one idea. Done is a claim, not a fact. Add agents to
a team and the bottleneck stops being doing the work. It becomes confirming the
work is real. Conductor is the project manager for that."

## 1:05–1:35 — One conversation to a team (the arc)

VISUAL: the app. Click "Plan a sprint." Show the plan: each commitment with its
`proof:` line. Point at the two the planner REFUSED ("no evidence requirement",
"trivially passing command proves nothing").

VO: "You describe a sprint once. Conductor turns it into commitments, and here's
the first tell: every commitment carries the check that will prove it, written
before any work starts. Work whose completion couldn't be proven isn't planned
at all. Approve, and it runs."

## 1:35–2:35 — THE CATCH, live on real git (Technical + Presentation)

VISUAL: run `python real_demo.py` in the terminal, or "Run six" in the UI. Slow
down here. Show the board: an agent reports done on slugify → REJECTED, evidence
detail "assert failed, not lowercased" → re-dispatched → verified → merged. Then
show the real git log and `slugify('Hello World') == 'hello-world'` on the base.

VO: "Watch the slugify task. The agent writes code and reports complete. But
Conductor doesn't take its word for it — it runs the check, in a real git
worktree. The check fails. Conductor catches the lie before any human sees it,
re-dispatches with the failure as context, and the retry passes. Only verified
work merges to the base branch. Maya never reviewed the wrong version. It never
existed on her repo."

## 2:35–3:15 — Waiting is optional (Creativity)

VISUAL: open the decision that needs a human. Show the three speculative
branches, one already merged, the cost ("$0.03").

VO: "Some things only a human can decide. Most tools stop and wait. Conductor
doesn't. While the decision is open, it builds every plausible answer overnight,
in isolated branches. Maya answers in twenty seconds — and the branch she chose
is already built and verified. The others cost three cents and are thrown away."

## 3:15–3:45 — Attention + the team (Design, completeness)

VISUAL: the Cost & trust view (held work with reasons, per-worker trust), then
the Team view (humans and agents, a delegate, probation).

VO: "Conductor only dispatches what Maya can actually review today; the rest is
held, with the reason. Agents aren't configured, they're hired: they join the
roster beside people, on probation, and earn a lighter check as they prove out."

## 3:45–4:15 — Built with Strands (Technical, make it impossible to miss)

VISUAL: a slide of the architecture: Strands agents (Planner, Recovery,
Compressor, Orchestrator) on Bedrock → the loop → real git. One line highlighted:
"No agent can mark anything done."

VO: "Conductor is a Strands Agents multi-agent system on Amazon Bedrock. Agents
do the judgment — planning, diagnosis. Deterministic code does the consequence —
verification, policy, trust. And the rule that makes it safe: no agent can mark
its own work done. The only path to done is a real check."

## 4:15–4:30 — Close (Presentation)

VISUAL: back to the empty decision surface: "Nothing needs you."

VO: "The best day is the one where Conductor stays quiet — the agents worked, the
checks passed, and nothing needed Maya. Conductor. The project manager for
humans and agents. It's open source, it runs cold with no keys, and the link's
below."

---

## Checklist the judges score against
- [ ] Problem stated in the first 30s, through a specific person (Maya)
- [ ] Working project demonstrated end to end (the catch, on real git)
- [ ] Strands named on screen and in VO
- [ ] Who it's for + why it matters, said out loud
- [ ] Under 5:00, public on YouTube/Vimeo
