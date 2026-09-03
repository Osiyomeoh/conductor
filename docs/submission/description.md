# Conductor — submission text

## The Devpost "text description" (paste this)

**Maya is a staff engineer. This morning she handed six tasks to her coding
agents: fix a webhook, migrate a table, write tests, do some research. By
lunch, all six came back marked "done." Three of them were wrong.**

Not broken-obviously wrong. Confidently, plausibly wrong. A slugify that forgot
to lowercase. A migration that passed its own script but not the schema test. An
agent does not get tired, it gets confidently lost, and it never tells you. So
Maya spends her afternoon doing the one thing agents made her do more of, not
less: reading their output to find out which "done" is a lie.

**Conductor is the project manager for that afternoon.** You describe a sprint
once. Conductor turns it into a working team of people and agents, dispatches
the work, and then does the thing no tracker does: it **verifies every result
against a real check before it believes the claim.** A slugify that fails its
test is caught, re-dispatched with the failure as context, and only reaches
Maya once it actually passes. She reviews verified work, not confident guesses.

It goes further:

- **Attention is budgeted.** Conductor only dispatches what Maya can actually
  review today. Twelve agent tasks nobody can check by Friday is debt, not
  throughput.
- **Waiting is optional.** When a decision needs a human, Conductor builds every
  plausible answer overnight in isolated git branches. Maya answers in twenty
  seconds; the winning branch is already verified and merged.
- **Agents are hired, not configured.** They join the roster beside people, on
  probation, and earn a lighter check as they prove out.

**Who it is for:** the engineer, founder, or small studio who now supervises AI
coding agents and spends their day checking whether the work is real.

**Why it matters:** every team adopting agents in 2026 hits this wall within a
month. The bottleneck stopped being *doing the work* and became *confirming the
work is real*. Conductor is built around that.

**How it works (Strands Agents):** Conductor is a Strands multi-agent system on
Amazon Bedrock. A Planner agent turns intent into commitments that each carry
their own evidence; a Recovery agent diagnoses failed checks; a Compressor
clusters escalations; an Orchestrator composes them as tools. Agents do the
judgment. Deterministic code does the consequence: the verification runner, the
policy gate, the trust ledger. **No agent can mark its own work done** — the
only path into "done" is a real check, run in a real git worktree, and its
verdict is final. Verified live end to end: a Strands worker wrote correct
Python into a git worktree, the check passed, and the branch merged.

**Built with:** Strands Agents SDK, Amazon Bedrock, Bedrock AgentCore (runtime
entrypoint + IaC included), FastAPI, React + TypeScript, real git worktrees,
event-sourced DynamoDB state.

**Run it cold (no keys, no AWS):** `python real_demo.py` runs the whole loop
against a real git repo, catches two planted wrong implementations, and merges
only the verified code. Live demo, public repo, and 41 tests in the README.
