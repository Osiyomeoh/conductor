# Conductor at 100x — the production user story

A north-star reference for what Conductor becomes at production scale. This is
the target, not the current build. The honest "where we are today" delta is at
the end, so this doubles as a roadmap. One sentence holds the whole thing:

> The best agent does not make the human manage more agents. It makes the human
> manage less, while increasing the truth of what actually got done.

Two invariants never bend, at any scale:
1. **Done is a claim, not a fact.** No language model has a path to "done." Only
   a real check, run in real isolation, can complete work.
2. **Human attention is the budget.** Agent labour is cheap and parallel; the
   reviewer is neither. Nothing is dispatched that cannot be reviewed.

---

## The cast

- **Alex** — founder and tech lead at an 8-person startup. Supervises three
  coding agents and four people. The primary user: spends judgment, not clicks.
- **Sarah** — product designer. A human teammate who owns ambiguous work.
- **Ravi** — backend engineer. Reviews agent PRs, sometimes goes silent for a day.
- **impl-agent, research-agent, migration-agent** — hired agents, each on
  probation until they earn trust for a kind of work.
- **Dana** — Alex's cofounder, occasional approver for money- and
  production-touching actions.

---

## Act 0 — Setup (once)

**Alex signs in with SSO.** Conductor authenticates through the company's
identity provider (Okta/Google/Cognito). No passwords are ever handled by
Conductor; it receives a signed token and reads the org and role from it. Alex
lands in the **Acme** workspace, scoped to their org, with role-based access:
Alex is an admin, Ravi and Sarah are members, Dana is an approver.

**Alex connects the org's real tools:**
- **GitHub** (or GitLab): OAuth grants Conductor scoped access to the two repos
  that matter. Conductor will work in branches and open **draft pull requests**,
  never force-push, never touch protected branches without a human merge.
- **CI**: the repo's existing test suite and checks are discovered, so a
  commitment's evidence can be "the real CI job passes," not a toy command.
- **Slack**: Conductor gets a bot user. Human tasks and the rare decision arrive
  as Slack messages with a crisp definition of done and a one-tap action; agent
  chatter never does.
- **Cloud** (optional): read-only cost and deploy signals, so "touches
  production" is a real, detectable condition the policy engine can block on.

**Alex builds the team.** People are invited by email and join with their own
SSO. Agents are **hired, not configured**: Alex picks a role (impl, research,
migration, docs) from a roster, each arrives **on probation**, and each will earn
a lighter check as it proves out on that kind of work. A delegate agent can act
on behalf of a specific person, scoped to what that person would sanction.

Setup is done. From here, Alex mostly talks and mostly waits.

---

## Act 1 — A sprint from a conversation

Monday, 9:00. Alex, walking to the office, opens Conductor on mobile and **speaks**:

> "Onboarding redesign by Friday, Sarah owns design. The payment webhook is
> dropping retries, fix it and prove it with a test. I want competitive research
> on three onboarding tools. And rewrite the empty-state copy. Agents can take
> the webhook, the research, and the copy."

Conductor transcribes it and, within seconds, returns a **plan**:
- Human and agent commitments are **separated**. Sarah owns the redesign
  (a human-review commitment). The webhook fix, the research, and the copy are
  dispatched to agents.
- **Every commitment carries the check that will prove it**, written before any
  work starts: the webhook fix's proof is the real regression test in CI; the
  research's proof is a document with three named tools and a decision matrix.
- Two vague asks ("improve onboarding", "tidy the code") are **refused** with a
  reason: no evidence requirement, so they were not planned at all.

Alex makes one edit by voice ("split the webhook fix from its regression test"),
then says "approve." The plan becomes a living system of commitments, and the
loop starts. Alex pockets the phone.

---

## Act 2 — The work dispatches itself

There are no forms, no manual assignment, no status meetings.

- Sarah gets a **Slack message**: the redesign commitment, its definition of
  done, and a link. She works in Figma; Conductor does not pester her.
- The agent commitments are dispatched into **isolated git worktrees** off the
  base branch. Each agent writes real code; none of them can mark its own work
  done.
- The **attention ledger** starts protecting Alex and Ravi. Conductor knows how
  much review capacity each has today and will not dispatch more verified work
  than they can actually absorb by Friday. Twelve agent PRs nobody can review is
  debt, not throughput, so surplus work is **held**, with the reason visible.
- The **board updates itself**. Nobody sets a status by hand.

---

## Act 3 — An agent lies, and is caught

11:40. The webhook agent finishes early and reports **done**, confidently. The
diff looks clean.

Conductor does not believe it. The **verification runner** checks out the
agent's branch in its worktree and runs the declared evidence: the real
regression test in CI. **It fails** — the retry backoff is off by one. In order:

1. The claim is **rejected**. It never reached Ravi's review queue.
2. The worktree is **destroyed**. The wrong code never touched the base branch,
   and never existed anywhere a human would see it.
3. The agent's **trust score for backend work drops** immediately.
4. **Recovery** begins automatically: a recovery agent diagnoses the failure
   (and can rule that the check itself was wrong), and re-dispatches with the
   failure as context. The retry passes CI. Only then does a **draft PR** open
   for Ravi, containing verified work.

Ravi reviews correct code, once. He never saw the wrong version. On the timeline,
the whole episode is three events and twelve cents of compute.

---

## Act 4 — The quiet protection of attention

Tuesday. Ravi is heads-down and goes silent on a commitment that is blocking
two others.

Conductor runs **graduated recovery** on its own: a soft nudge, then a firmer
one, then a proposal to reassign, without ever escalating to Alex. A second agent
is running slow; Conductor holds its dependents rather than piling unreviewable
work downstream.

The **decision surface stays empty** all morning, because nothing there actually
needs a human's judgment. Then, at 2:10, exactly one item appears, ranked by
what it unblocks:

> **Decide the onboarding paywall position.**
> Unblocks 4 commitments and frees ~90m of review. Two viable options, and what
> each already costs.

It arrives in Slack. Alex reads it for twenty seconds and answers once.
Everything else was already handled.

---

## Act 5 — The night the system worked while Alex slept

That paywall decision had been open since Monday. Rather than wait, Conductor had
already **forked the plan across every plausible answer** and built each branch
in isolation overnight, running their checks, discarding the losers. Total cost:
a few cents. Human attention spent before the moment of choice: zero.

So when Alex picks "paywall after the first value moment," the follow-on work for
that answer is **already built and verified**, and merges immediately. The other
branches are thrown away. Waiting was optional.

---

## Act 6 — The quiet morning

Friday, 8:30. Alex opens Conductor. The decision surface reads **"Nothing needs
you."**

- The **board is accurate** and nobody updated a status all week.
- The **trust ledger** reflects real performance: impl-agent earned a lighter
  check on backend work after ten clean verifications; migration-agent is still
  on probation.
- **Cost per verified commitment** is visible, and the week came in under the
  budget Alex set.
- The **event log** can answer any "why is this done?" — every claim, check,
  verdict, merge, and hold, in order, attributed. It is the system of record.
- Alex's **attention was spent only on real decisions**: two, all week.

The redesign shipped. The webhook is fixed and proven. The research is on Alex's
desk. And the best day was the quiet one.

---

## The production capabilities behind the story

**Identity and access.** SSO/OIDC (Okta, Google, Cognito). Org and workspace
scoping. Role-based access: admin, member, approver, viewer. Every action is
attributable to a person or a named agent acting for a person.

**Real integrations.**
- Git host (GitHub/GitLab): scoped OAuth, work in branches, **draft PRs**, never
  force-push, respect branch protection and CODEOWNERS.
- CI: a commitment's evidence can be a real pipeline job, not a toy command.
- Slack/email/mobile: human tasks and decisions delivered where people already
  are, with one-tap actions; agent noise stays out.
- Issue trackers (Linear/Jira): commitments sync both ways, so Conductor is the
  brain and the tracker stays the shared record.

**The team as a first-class model.** Invite humans; hire agents from a roster
(and, at the far edge, an agent **marketplace** where specialist agents are rated
by their verified track record, not their marketing). Probation and earned trust
per kind of work. Delegate agents that act for a specific person within scopes.

**The verification substrate.** Isolated git worktrees; real checks (tests,
commands, schema, HTTP, human review); pass merges, fail is destroyed. This is
the one thing that never becomes decorative.

**Attention and policy.** A per-person attention budget that gates dispatch. A
policy engine that scores risk (irreversible, external, cost, low trust) and
routes AUTO / APPROVE / BLOCK, with hard blocks that never proceed at any
autonomy (touches production, touches money, speaks to a customer). Autonomy is a
dial the org sets and agents earn.

**Speculation.** While a decision waits, build every plausible answer in
isolation, verify them, and discard the losers, so the chosen path is already
real. Bounded by a cost ceiling.

**Durability and scale.** Event-sourced state on DynamoDB, partitioned per
tenant, replayable, resumable. Multi-instance and highly available (the seq
counter is atomic, state is shared, no instance is special). Point-in-time
recovery. Multi-project and multi-org.

**Cost governance.** Per-role model pricing (cheap models for volume, capable
models for judgment), a live cost ledger, per-verified-commitment accounting, and
hard budget ceilings with alarms. Spend is a first-class, visible number.

**Observability.** Full tracing (the control loop as spans), dashboards for
throughput, catch rate, held work, and attention utilization, and alarms on the
things that matter (catch rate spiking, a worker's trust collapsing, budget
nearing a ceiling).

**Security.** Secrets in a secrets manager, never in env or code. Least-privilege
task roles. Every agent action sandboxed. An audit trail that is the event log
itself. No path from a model to production without a human on the money- and
production-touching actions.

---

## Failure modes the product handles by design

- **An agent is confidently wrong.** Caught by verification before any human
  sees it; trust drops; recovery re-dispatches. (The core loop.)
- **A human goes silent.** Graduated recovery and reassignment, without
  escalating until policy says a real decision is required.
- **A decision blocks progress.** Speculation builds the answers ahead of time;
  the human answers once and the work is already done.
- **Too much verified work for the reviewers.** Held with a reason, not dumped on
  a queue nobody can clear.
- **A risky action** (deploy, refund, customer email). Blocked by policy,
  escalated to an approver, never auto-executed.
- **A cost spike.** Budget ceilings and alarms; speculation is bounded; the loop
  degrades to held rather than runaway spend.
- **A restart or a lost instance.** State resumes from the durable log; no work
  or trust is lost.

---

## Reality delta — where we are today vs this 100x target

Honest accounting, so this reference is not mistaken for the current build.

**Real today (verified, deployed):**
- Voice **dictation** into the planner; live LLM planning that reads intent and
  attaches a proof to every commitment, refusing the unprovable.
- The verification loop and **the catch**, on real git worktrees with real
  checks, deployed on AWS App Runner and invocable on Bedrock AgentCore Runtime.
- Decisions ranked by attention freed; speculative branches; the attention
  budget; the trust ledger; cost accounting; the event log.
- **Local** real-repo execution (gated), isolated worktrees, merge only on a
  passing check, never pushes.
- Per-visitor isolation, rate limits, input caps, event-sourced DynamoDB
  persistence for real tenants.

**Not built yet (the 100x gap):**
- **SSO/OIDC** login and RBAC (the auth boundary exists with a marked IdP
  integration point; JWKS validation is stubbed).
- **GitHub/GitLab** integration: OAuth, clone, draft PRs, branch protection. Today
  it is a local filesystem path only, no GitHub API, no push.
- **Slack/email/mobile** delivery of tasks and decisions. No Slack code exists.
- **Inviting humans and hiring agents from the UI.** The roster is seeded; the
  system can propose a hire but a user cannot yet act on it. Onboarding's "invite
  your team" is cosmetic.
- **Voice conversation** (two-way dialogue, TTS). Today voice is one-way
  dictation.
- CI-as-evidence, issue-tracker sync, an agent marketplace, cloud cost/deploy
  signals, multi-instance HA, full tracing dashboards, and budget alarms.

The through-line: the **hard, differentiating core is real** — verification,
attention, speculation, policy, trust, on real git and real AWS. The **100x gap
is the collaboration and integration surface** around that core: identity, the
git host, the delivery channels, and a team you actually build rather than one
that ships seeded.
