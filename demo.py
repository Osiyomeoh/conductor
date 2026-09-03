"""End-to-end run. Nothing is mocked: workers write real files, the verifier
runs real commands against them."""

from conductor.models import Status
from conductor.world import build

C = ["\033[0m", "\033[2m", "\033[1m", "\033[32m", "\033[31m", "\033[33m"]
R, D, B, G, RED, Y = C


def board(c, title):
    print(f"\n{B}{title}{R}")
    for cm in sorted(c.graph, key=lambda x: x.title):
        col = {Status.DONE: G, Status.REJECTED: RED, Status.HELD: Y,
               Status.ESCALATED: Y}.get(cm.status, D)
        spec = f" {D}[spec]{R}" if cm.speculative_for else ""
        print(f"  {col}{cm.status.value:<13}{R} {cm.title[:58]}{spec}")


def main():
    c = build()
    print(f"{B}CONDUCTOR{R}  {D}done is a claim, not a fact{R}")

    c.run(ticks=6)
    board(c, "After six ticks, unattended")

    print(f"\n{B}Decision surface{R}  {D}(the only thing Sam ever sees){R}")
    for d in c.surface.queue():
        print(f"  {Y}{d.id}{R} {d.root_question}")
        print(f"      unblocks {d.unblock_value} items | options: {', '.join(d.options)}")
        if d.merged_from:
            print(f"      {D}compressed from {len(d.merged_from)+1} escalations{R}")
    print(f"  {D}{c.surface.compression_ratio}{R}")

    q = c.surface.queue()
    if q:
        d = q[0]
        print(f"\n{B}Sam answers one question{R}: {d.root_question}")
        print(f"  {D}{c.speculation.report(d.id)}{R}")
        c.answer(d.id, d.options[0])
        c.run(ticks=6)

    board(c, "After the answer")

    m = c.metrics
    print(f"\n{B}What the loop actually did{R}")
    print(f"  dispatched            {m.dispatched}")
    print(f"  claims of completion  {m.claims}")
    print(f"  {RED}claims rejected       {m.claims_rejected}{R}  {D}caught by evidence, not by Sam{R}")
    print(f"  {G}verified done         {m.verified}{R}")
    print(f"  escalations raised    {m.escalations_raised}")
    print(f"  {B}times Sam interrupted {m.interruptions}{R}")
    print(f"  held for attention    {m.held}")
    print(f"\n{B}Trust, learned from outcomes{R}")
    for rid in c.graph.resources:
        line = c.trust.summary_line(rid)
        if "no history" not in line:
            print(f"  {rid:<16} {line}")
    print(f"\n{B}What it cost{R}")
    c_ = c.cost
    b = c_.by_outcome()
    print(f"  total spent           ${c_.total:.4f}")
    print(f"  {G}on work that passed   ${b.get('verified',0):.4f}{R}")
    print(f"  {RED}on claims that failed ${b.get('rejected',0):.4f}{R}  {D}never billed, never reviewed by Sam{R}")
    print(f"  {D}on discarded branches ${b.get('discarded',0):.4f}{R}  {D}the price of not waiting overnight{R}")
    print(f"  {B}cost per verified item ${c_.cost_per_verified():.4f}{R}")
    print(f"\n{B}Spend by model{R}  {D}cheap models do the volume, capable ones the judgment{R}")
    for mid, usd in sorted(c_.by_model().items(), key=lambda x: -x[1]):
        print(f"  {mid:<46} ${usd:.4f}")

    print(f"\n{B}Attention{R}")
    for b in c.dispatcher.budgets.values():
        print(f"  {b.summary()}")
    print(f"\n{B}Event log{R}")
    for e in c.events[-10:]:
        print(f"  {D}{e[11:]}{R}")


if __name__ == "__main__":
    main()
