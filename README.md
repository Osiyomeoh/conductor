# Conductor

**A project manager for teams of humans and AI agents.**

Every project tool ever built assumes labour is expensive and judgment is free.
Agents inverted that. Labour is now cheap and parallel; judgment is not.
Conductor spends the first to buy back the second.

Built with the [Strands Agents SDK](https://strandsagents.com) on Amazon Bedrock,
deployed to Bedrock AgentCore Runtime.

---

## The problem

Add AI agents to a team and output goes up sharply. So does a failure mode that
humans rarely produce: **an agent reports done, confidently, having produced
something plausible and wrong.** It does not get tired, it gets confidently lost,
and it never tells you.

Every tracker on the market records that as success, because completion is a
status a worker sets. That was defensible when workers were people who feel
embarrassment. It is not defensible now.

So the bottleneck moves. It stops being *doing the work* and becomes *confirming
the work is real*, and the scarce resource stops being engineering time and
becomes human attention. No project tool models either.

## What Conductor does differently

**Done is a claim, not a fact.** Every commitment declares, at plan time, the
evidence that would prove it: a test that must pass, an endpoint that must
respond, a file that must exist. The verification runner executes that check
before status can reach `done`. A commitment with no evidence requirement fails
closed, because an unverifiable task is a planning defect, not a free pass.

**Human attention is the budgeted resource.** Dispatch is throttled by the
reviewer's remaining review capacity, not by worker availability. Work nobody can
check today is *held*, with the reason. Twelve agent tasks you cannot review by
Friday is not throughput, it is debt with a friendly status colour.

**Waiting is optional.** When the project stalls on a decision only a person can
make, the plan forks across every plausible answer and builds all of them in
isolation overnight. When you answer, the chosen branch is not queued, it is
already verified. The losers are discarded. In the seeded sprint that costs about
24 cents and buys back a night.

**Nine escalations are usually two questions.** Escalations are clustered by the
uncertainty behind them, asked once, and ranked by how much work each answer
unblocks.

**Trust is earned and priced.** Verification depth is tracked per worker per kind
of work, from outcomes only. It rises slowly and falls immediately, so the system
verifies less as it learns more and snaps back to deep checks the moment a worker
misses.

**The team is hired, not configured.** An agent teammate is declared as a job
description and joins the board beside the people, on probation, with no trust.
An agent can also act *for* a person: it inherits that principal's scopes, can
never exceed them, and its output is reviewed by them. Delegation moves the
labour, not the accountability.

## Architecture

One line decides where every component lives: **language models do judgment,
deterministic code does consequence.**

```
ENTRYPOINT      AgentCore Runtime, async task — the loop runs between invocations
    │
JUDGMENT        Strands agents on Bedrock
    │           Planner · Compressor · Recovery · Orchestrator
    │           ✗ no agent can mark anything done
    │ proposals only
CONTROL LOOP    verify → recover → surface judgment → compress → speculate → dispatch
    │           idempotent per tick, every change appended to an event log
    ├── Verification runner    command · file · http · human review
    ├── Attention ledger       dispatch capped by reviewer capacity
    ├── Speculation engine     forks the plan across open decisions
    ├── Decision surface       compressed, ranked by unblock value
    ├── Trust ledger           earned slowly, lost at once
    └── Cost ledger            priced per commitment, branch and decision
    │
POLICY GATE     AUTO / APPROVE / BLOCK on every action reaching the world
    │           hard blocks: production · money · customer-facing speech
ROSTER          hire() · probation · principal/scopes · elastic headcount
EXECUTION       isolated branch per agent; nothing merges until evidence passes
STATE           commitment graph, risk rescored every tick
```

Full diagrams: [`docs/architecture.html`](docs/architecture.html).

The one edge worth tracing is the one that does not exist: **there is no path from
the judgment layer to `done`.** Agents propose, the loop dispatches, and only the
verification runner can complete anything. Its verdict is not overridable by a
model.

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# the deterministic core, no AWS needed
.venv/bin/python demo.py          # a seeded sprint, start to finish
.venv/bin/python roster_demo.py   # hiring, delegation, scope inheritance
.venv/bin/python -m pytest tests/ -q
```

The decision surface, which is the only part a person looks at:

```bash
.venv/bin/python serve.py            # http://127.0.0.1:7616
```

It shows what needs you, what is held and why, what each question unblocks and
how many branches were already built against it, where the attention budget
went, and what the run cost. On a good day it says "Nothing needs you."

For the Strands agents you need AWS credentials and Anthropic models enabled in
Bedrock:

```bash
aws configure --profile conductor     # region us-west-2
.venv/bin/python check_aws.py         # preflight: identity, access, one real call
```

Conductor binds to a named profile on purpose and fails loudly rather than
falling through to `default`, because it runs agents that write files and execute
commands. Set `CONDUCTOR_AWS_PROFILE=""` to use ambient credentials deliberately,
which is correct inside AgentCore Runtime where the task role is the right
identity.

### Deploying to AgentCore

```bash
npm install -g @aws/agentcore
agentcore create --name Conductor --framework Strands --model-provider Bedrock
agentcore dev
agentcore deploy
agentcore invoke '{"action": "state"}'
```

Actions: `state`, `tick`, `run`, `answer`, `plan`, `ask`.

## Persistence and replay

The loop is idempotent per tick, so the durable thing is not the graph, it is
the sequence of facts that produced it. Every meaningful transition is appended
to an event log: planned, hired, dispatched, held, claimed, verified, rejected,
escalated, answered, speculated, discarded.

```bash
.venv/bin/python replay_demo.py
```

That runs a sprint, persists it, then rebuilds the entire graph from the log
alone and checks the result against the live run. No workers run, no checks
execute, no money is spent, and the reconstruction is exact.

Three backends sit behind one interface: in-memory, JSONL, and DynamoDB
partitioned by tenant and sorted by sequence, with a conditional write so a
replayed tick cannot double-record a fact. Events carry a tenant, so one log
holds many teams without the graph ever seeing another team's work.

This buys three things Conductor specifically needs. The loop survives a restart
mid-sprint. "Why is this done?" has an answer with a timestamp on it, which
matters most for the one transition the whole product turns on. And a demo can
replay a real run without dispatching live agents at it.

## Cost

Conductor deliberately spends compute to save attention, so the spending is
measured rather than asserted. Models are selected per role: workers run on Haiku
because they are the entire cost curve, judgment roles stay on Sonnet because
writing a check whose failure is *meaningful* is the hardest call in the system.

Measured on the seeded sprint, same run, only the model policy changed:

| | all Sonnet | per-role |
|---|---|---|
| total | $2.0381 | **$0.6794** |
| per verified commitment | $0.4076 | **$0.1359** |

Two numbers matter more than the total: cost per *verified* commitment, which is
what you actually got, and spend on *rejected* claims, which is what the
verification layer saved you from reviewing by hand.

Prices in `conductor/models_config.py` are placeholders until measured against a
real bill.

## Status

Working: the state, execution, policy, roster and control-loop layers, with 22
invariant tests. The seeded sprint runs end to end with real shell verification.

Not yet exercised against Bedrock: the four Strands agents. Written against the
verified SDK API, but no live model call has been made.

Stubs: no board or chat adapters.

## Licence

MIT. See [LICENSE](LICENSE).
