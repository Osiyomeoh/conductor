"""Adding teammates: an agent for the team, and an agent for a person."""

from conductor.roster import AgentSpec, Roster
from conductor.world import build

B, D, R, Y = "\033[1m", "\033[2m", "\033[0m", "\033[33m"

c = build()
roster = Roster(graph=c.graph, trust=c.trust)

print(f"{B}Team before{R}")
for r in c.graph.resources.values():
    print(f"  {r.type.value:<6} {r.id}")

# Sam has scopes; his delegate can never exceed them.
c.graph.resources["human_sam"].scopes = ["repo:read", "repo:write:branch", "docs:write"]

# 1. A team agent.
roster.hire("agent_docs", "docs-agent", AgentSpec(
    purpose="Turn merged changes into release notes and changelog entries.",
    work_kinds=["content", "docs"],
    scopes=["repo:read", "docs:write"]))

# 2. An agent that belongs to a person.
roster.hire("agent_sam_delegate", "sam's delegate", AgentSpec(
    purpose="Handle Sam's routine review prep: summarise diffs, draft replies.",
    work_kinds=["review-prep"],
    scopes=["repo:read", "repo:write:branch", "docs:write", "prod:deploy"]),
    principal="human_sam")

print(f"\n{B}Team after{R}")
for r in c.graph.resources.values():
    tag = f" {D}(acts for {r.principal}){R}" if r.principal else ""
    prob = f" {Y}[probation]{R}" if r.type.value == "agent" and r.probation else ""
    print(f"  {r.type.value:<6} {r.id}{tag}{prob}")
    if r.spec:
        print(f"         {D}scopes: {', '.join(r.scopes)}{R}")

print(f"\n{B}Scope inheritance{R}")
d = c.graph.resources["agent_sam_delegate"]
print(f"  requested prod:deploy, Sam does not hold it")
print(f"  granted: {d.scopes}")
print(f"  {D}an agent cannot hold a scope its principal lacks{R}")

print(f"\n{B}Accountability{R}")
print(f"  work by agent_sam_delegate is reviewed by "
      f"{roster.reviewer_for('agent_sam_delegate')}")
print(f"  {D}delegation moves the labour, not the accountability{R}")

c.run(ticks=4)
print(f"\n{B}Elastic headcount{R}")
for kind, n in roster.bottlenecks(min_waiting=1):
    p = roster.propose_hire(kind, n)
    print(f"  {Y}{p['question']}{R}")
    print(f"    options: {', '.join(p['options'])}")

print(f"\n{B}Probation{R}")
print(f"  agent_docs graduated: {roster.graduate('agent_docs')} {D}(no passes yet){R}")
for _ in range(5):
    c.trust.record("agent_docs", "content", True)
print(f"  after 5 clean verifications: {roster.graduate('agent_docs')}")
print(f"  evidence depth now: {c.trust.evidence_depth('agent_docs', 'content')}")
