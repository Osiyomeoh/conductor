# Conductor — screens (captured live on AWS App Runner)

All images below were captured against the permanent public deployment at
**https://pe6euudszs.us-west-2.awsapprunner.com** (AWS App Runner), not a local
server. Regenerate with `.venv/bin/python scripts/capture-apprunner.py`.

## Landing
![Landing hero](../shots/apprunner-landing.png)

Full page: [apprunner-landing-full.png](../shots/apprunner-landing-full.png)

## Pricing (public page)
![Pricing](../shots/apprunner-pricing.png)

## App — Home ("Nothing needs you")
![App home](../shots/apprunner-app-home.png)

The best day is the quiet one: the agents worked, the checks passed, nothing
needed a human.

## App — Board
![Board](../shots/apprunner-app-board.png)

Ten commitments in their real states after a run: `ESCALATED` (a decision a
human must make), `HELD` with the reason ("reviewer has 0m left, this needs
20m") — attention budgeting in the open — and `SPEC` follow-on work forked from
a pending decision.

## App — Decisions
![Decisions](../shots/apprunner-app-decisions.png)

## App — Activity stream
![Activity](../shots/apprunner-app-activity.png)

Every verify, catch, merge and hold, in order, attributed to the worker.

## App — Team (people and agents)
![Team](../shots/apprunner-app-team.png)

## App — Cost & trust
![Cost and trust](../shots/apprunner-app-cost.png)

## App — Real execution (real git, real checks)
![Real execution](../shots/apprunner-real-exec.png)

Not a simulation of the guarantee, the guarantee itself: each task runs in its
own git worktree, the check runs as a real command, and only a branch that
passes is merged. The base branch's history shows real merge commits, and the
source on the base is the verified version — `slugify.py` is the correct,
lowercased implementation, because the confident-but-wrong first attempt was
caught and never merged. Toggle "live agent" to have a Strands agent on Gemini
write the code instead of the deterministic worker.
