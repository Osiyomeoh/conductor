# Conductor

**A project manager for teams of humans and AI agents.**

Describe a sprint once. Conductor turns it into a working team of people and
agents, dispatches the work, verifies every result against a real check, and
tracks all of it. It surfaces only when a decision needs a human.

Built with the **[Strands Agents SDK](https://strandsagents.com)** on Amazon
Bedrock (with a Gemini provider path), and deployable to Amazon Bedrock
AgentCore Runtime.

**Track:** Professional Agents. **Live demo:** run `python serve.py` and open
`http://127.0.0.1:7616` (see *Running it*).

---

## The problem

Add AI agents to a team and output goes up sharply. So does a failure mode
humans rarely produce: **an agent reports done, confidently, having produced
something plausible and wrong.** It does not get tired, it gets confidently
lost, and it never tells you.

Every project tracker records that as success, because completion is a status a
worker sets. That was defensible when workers were people who feel
embarrassment. It is not defensible now.

So the bottleneck moves. It stops being *doing the work* and becomes *confirming
the work is real*, and the scarce resource stops being engineering time and
becomes human attention. No project tool models either.

**Who it is for:** the engineer, founder, or small studio who now supervises AI
coding agents and spends the day checking whether the agents' work is actually
real.

## What Conductor does differently

The premise: labour is now cheap and parallel, judgment is not, so Conductor
spends the first to buy back the second.

- **Done is a claim, not a fact.** Every commitment declares, at plan time, the
  evidence that would prove it: a test that must pass, a file that must exist,
  an endpoint that must respond. A verification runner executes that check
  before status can reach `done`. A commitment with no evidence fails closed.

- **Human attention is the budgeted resource.** Dispatch is throttled by the
  reviewer's remaining review capacity, not by worker availability. Work nobody
  can check today is *held*, with the reason.

- **Waiting is optional.** When the plan stalls on a decision only a person can
  make, Conductor forks it across every plausible answer and builds them all in
  isolation overnight. When you answer, the chosen branch is already verified;
  the losers are discarded for a few cents.

- **Nine escalations are usually two questions.** Escalations are clustered by
  the uncertainty behind them and ranked by how much work each answer unblocks.

- **Trust is earned and priced.** Verification depth is tracked per worker per
  kind of work, from outcomes only. It rises slowly and falls immediately.

- **The team is hired, not configured.** Agents join the roster beside people,
  on probation, and an agent can act *for* a person, inheriting their scopes and
  never exceeding them.

## Strands Agents

Conductor is a Strands multi-agent system. Language models do judgment;
deterministic code does consequence.

| Agent (Strands) | Role |
|---|---|
| **Planner** | Turns intent into commitments that each carry their own evidence. `structured_output`. |
| **Compressor** | Clusters escalations into root questions. |
| **Recovery** | Diagnoses a failed check, and may rule the check itself wrong. |
| **Orchestrator** | Agents-as-tools; reads board, queue, attention, trust. Cannot mark anything done. |
| **StrandsWorker** | A real agent teammate, built from an `AgentSpec`, writing real code into a git worktree. |

Deterministic and auditable (not agents): the verification runner, policy gate,
attention ledger, trust ledger. **No agent can mark anything done** — the only
path into `done` is the verification runner, and its verdict is not overridable.

## Architecture

```
FRONTEND  React + TypeScript SPA (web/)               served at /, /product, /app ...
  typed API client · landing · onboarding · 5 marketing pages · the app shell
        │
BACKEND   FastAPI ASGI service (conductor/asgi.py)     per-tenant · auth boundary · logging
        │
JUDGMENT  Strands agents on Bedrock/Gemini             Planner · Compressor · Recovery · Orchestrator
        │ proposals only (no agent can mark done)
LOOP      verify → recover → surface → compress → speculate → dispatch   (idempotent, event-sourced)
        ├── verification runner   command · file · http · human review
        ├── attention ledger      dispatch capped by reviewer capacity
        ├── speculation engine    forks the plan across open decisions
        ├── trust ledger          earned slowly, lost at once
        └── cost ledger           priced per commitment, branch, decision
        │
GATE      policy engine           AUTO / APPROVE / BLOCK on every action to the world
        │
EXECUTION real git worktrees      nothing merges to base until evidence passes
        │
STATE     event-sourced graph     resumable · replayable · DynamoDB / JSONL / memory
```

Full diagrams: [`docs/architecture.html`](docs/architecture.html).

## Running it

A stranger can run it cold, with no AWS and no API keys, via the deterministic
demo. The engine is real; only the language model is swapped for a fixed worker.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. The whole loop against a REAL git repo, no model, no network:
.venv/bin/python real_demo.py

# 2. A seeded sprint, start to finish, in the terminal:
.venv/bin/python demo.py

# 3. The tests (41 invariants):
.venv/bin/python -m pytest tests/ -q
```

### The app (landing, onboarding, workspace, marketing pages)

```bash
.venv/bin/python serve.py          # uvicorn on http://127.0.0.1:7616
```

Open `http://127.0.0.1:7616`: the landing page, `/product` `/pricing`
`/customers` `/now` `/contact` (public), `/signup` (onboarding), and `/app`
(the workspace). Nothing runs until you drive it from the UI.

### Live agents

Conductor is model-agnostic (Strands). Bedrock is the default provider; set
Gemini to run live agents on a working quota:

```bash
echo 'GEMINI_API_KEY=your_key' > .env          # gitignored
set -a && . ./.env && set +a
CONDUCTOR_PROVIDER=gemini .venv/bin/python serve.py     # or: check_aws.py for Bedrock
```

Verified live end to end: a Strands worker wrote correct Python into a real git
worktree, the evidence check passed, and the branch merged into the base.

### Rebuilding the frontend

The compiled `web/dist` is committed, so `serve.py` runs with no Node step. To
change the UI:

```bash
cd web && npm install && npm run build
```

## Deploying to production

The service (`conductor.asgi:app`) has per-tenant isolation, an auth boundary,
durable state and request logging. Artifacts are in `deploy/`:

```bash
aws cloudformation deploy --template-file deploy/cloudformation.yaml \
  --stack-name conductor --capabilities CAPABILITY_NAMED_IAM      # DynamoDB + task role
npm install -g @aws/agentcore
agentcore create --name Conductor --framework Strands --model-provider Bedrock
agentcore deploy
```

`conductor/agentcore_entry.py` is the AgentCore Runtime handler; the loop keeps
running between invocations via `async_task`. `.github/workflows/ci.yml` runs
the test suite on every push.

## Cost

Cheap models do the volume, capable models do the judgment. On the seeded
sprint, per-role model selection cut cost from **$0.41 to $0.14 per verified
commitment** with planning quality unchanged. Prices in
`conductor/models_config.py` are placeholders until measured against a bill.

## Status (honest)

- **Working:** the full engine (verification, attention, speculation, trust,
  policy, roster, cost, event-sourced persistence, real git execution), the
  React + TypeScript frontend, the FastAPI service, 41 invariant tests.
- **Verified live on Gemini.** The Bedrock path is wired and correct; live
  Bedrock calls are currently throttled by a new-account daily token quota.
- **Prototype:** the sign-in flow collects no real credentials; auth enforcement
  and the IdP integration point exist but are not wired to a live provider.

## Licence

MIT. See [LICENSE](LICENSE).
