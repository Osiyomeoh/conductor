"""Run the decision surface against a live sprint."""
from conductor.server import serve
from conductor.world import build

c = build()
c.run(ticks=3)          # give it something to show
serve(c, port=7616)
