# Conductor, 5-minute demo video, script and shot list

One theme, said in one sentence:

> The best agent does not make the human manage more agents. It makes the human
> manage less, while increasing the truth of what actually got done.

Tone: calm, precise, slightly intense. No hype. Clarity and inevitability. One
voice. Music low and minimal, tense then resolving. Prefer real screen
recordings over slides. The caught lie is the emotional peak and must be real or
tightly edited.

Recording note: the deterministic path runs cold with no keys, so nothing
depends on a model quota. `python real_demo.py` for terminal proof; the live app
at https://pe6euudszs.us-west-2.awsapprunner.com drives the UI beats.

Structure (5:00):

| time | section | length |
|---|---|---|
| 0:00 to 0:25 | the problem | 25s |
| 0:25 to 3:20 | the live flow | 2m55 |
| 3:20 to 4:15 | architecture, why it is different | 55s |
| 4:15 to 4:45 | live demo and AgentCore | 30s |
| 4:45 to 5:00 | close | 15s |

---

## 0:00 to 0:25, the problem

VISUAL: dark title card, Conductor, subtitle "a project manager for teams of
humans and agents." Quick cuts of 2026 pain: Slack threads full of "done", an
agent PR that looks right and is wrong, a tired founder at a board at 11pm.

VO: "We added agents. Output exploded. So did a new kind of failure: agents that
report done, with total confidence, while being wrong. The bottleneck stopped
being labour. It became confirming the work is real, and protecting the one
resource that still cannot scale: human attention."

ON SCREEN: "Done is a claim. Human attention is the budget."

## 0:25 to 0:50, intent becomes a plan

VISUAL: Alex drops a messy voice note. "Onboarding redesign by Friday, Sarah owns
design. Payment webhook is broken. Need competitive research on three tools.
Landing page copy. Agents can take the research and the tests." Conductor turns
it into a clean plan: human commitments and agent commitments separated, each
carrying its proof requirement, editable. Alex makes two edits and approves.

VO: "You speak. Conductor turns intent into a living system of commitments, each
one with the check that will prove it. You keep the judgment. Everything else
becomes infrastructure."

## 0:50 to 1:40, the agent lies, and is caught (the climax)

VISUAL: an agent finishes early and reports done. The output looks good. The
verification runner runs the declared check, in a real git worktree. It fails.
The claim is rejected. The worktree is destroyed. The agent's trust on this kind
of work drops. Recovery re-dispatches, and the retry passes and merges. Cut to
the real git log and the correct file on the base branch.

ON SCREEN: "No path from any language model to done. Only the verification runner
completes work."

VO: "This is the moment most tools miss. An agent can be confidently wrong.
Conductor never lets a claim become reality until the evidence passes. The wrong
work is discarded before any human sees it."

## 1:40 to 2:20, the silent human, protected attention

VISUAL: a human teammate goes quiet, a second agent is slow. Conductor runs
graduated recovery, soft then firmer, without escalating. The decision surface
stays empty. Then one clean item appears, ranked by what it unblocks: "unblocks 4
commitments, frees 40m of your review." Alex answers once.

VO: "Most problems are solved without you. When something needs your judgment, it
arrives clean, ranked, with options. Everything else was already handled."

## 2:20 to 2:55, speculation, the night it worked while you slept

VISUAL: one open decision was blocking progress. Conductor had already forked the
plan across the plausible answers, built the branches in isolation, verified
them, and discarded the losers. Cost shown, a few cents. Attention spent, zero
until the moment of choice.

VO: "Waiting is optional. Conductor spends cheap parallel compute so that when you
decide, the work is already real."

## 2:55 to 3:20, the human is lighter

VISUAL: the board is accurate with nobody updating status, the trust ledger is
current, cost per verified commitment is visible, the event log is complete, the
decision surface reads "Nothing else needs you."

VO: "The board updated itself. Reality was verified. Attention was protected. The
human spent judgment only where it mattered."

## 3:20 to 4:15, architecture, why it is different

VISUAL: a clean diagram with one highlighted edge: there is no path from any
language model to done. Callouts: commitment graph, verification runner
(deterministic), attention ledger, speculation engine, policy gate, trust ledger,
event-sourced control loop.

VO: "Language models do judgment. Deterministic code does consequence. That single
separation is what makes the system trustworthy. No agent can mark its own work
done."

## 4:15 to 4:45, live demo and AgentCore

VISUAL: the live app URL, the Real execution view running one real tick against a
real git repo, then the AgentCore runtime ARN and one invocation returning real
state. "This is not a mock. This runs."

VO: "Built with the Strands Agents SDK. Deployed on Amazon Bedrock AgentCore
Runtime. Live demo available to judges."

## 4:45 to 5:00, close

VISUAL: black screen. "Conductor. Spends cheap labour to buy back expensive
attention." Smaller: "Agents for Humans."

VO: "The best agent does not make the human manage more. It makes the human manage
less, while increasing the truth of what actually got done."

---

## The checklist judges score against
- [ ] Problem stated in the first 30s, through a specific person (Alex)
- [ ] Working project shown end to end (the catch, on real git)
- [ ] Strands named on screen and in VO; AgentCore deployment shown
- [ ] Who it is for and why it matters, said out loud
- [ ] Under 5:00, public link on screen
