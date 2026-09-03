import { useEffect, useRef, useState } from "react";
import "./landing.css";

type Row = { chip: string; label: string; title: string; why: string; right: string };
const SCRIPT: Row[] = [
  { chip: "s-done", label: "done", title: "Fix the payment webhook retry", why: "grep -q RETRY_OK webhook.txt · passed", right: "impl-agent" },
  { chip: "s-held", label: "held", title: "Migrate the onboarding events table", why: "reviewer has 0m left · waiting", right: "25m" },
  { chip: "bad", label: "", title: "Implement slugify(text)", why: "", right: "impl-agent" },
  { chip: "s-done", label: "done", title: "Competitive research on three tools", why: "research.txt · passed", right: "research-agent" },
];

// The self-running mini control room — the loop catching a bad claim.
function useStage() {
  const rowsRef = useRef<HTMLDivElement>(null);
  const [title, setTitle] = useState("One thing needs you.");
  const [figs, setFigs] = useState({ caught: 0, ver: 0, held: 0 });

  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setFigs({ caught: 1, ver: 3, held: 1 }); setTitle("Nothing needs you."); return;
    }
    let alive = true;
    const el = rowsRef.current!;
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const mk = () => {
      const r = document.createElement("div");
      r.className = "srow";
      r.innerHTML = `<span class="schip s-run">dispatched</span><div><div class="stitle"></div><div class="swhy"></div></div><span class="sright"></span>`;
      el.appendChild(r); requestAnimationFrame(() => r.classList.add("in")); return r;
    };
    const set = (r: HTMLElement, chip: string, label: string, t: string, why: string, right: string) => {
      const c = r.querySelector(".schip")!; c.className = "schip " + chip; c.textContent = label;
      r.querySelector(".stitle")!.textContent = t;
      r.querySelector(".swhy")!.textContent = why;
      r.querySelector(".sright")!.textContent = right;
    };
    let caught = 0, ver = 0, held = 0;
    const bump = () => setFigs({ caught, ver, held });
    async function run() {
      if (!alive) return;
      el.innerHTML = ""; caught = ver = held = 0; bump(); setTitle("One thing needs you.");
      for (const item of SCRIPT) {
        if (!alive) return;
        const r = mk(); set(r, "s-run", "dispatched", item.title, "agent working…", item.right);
        await sleep(700);
        if (item.chip === "bad") {
          set(r, "s-run", "dispatched", item.title, "agent reports complete", item.right); await sleep(650);
          r.classList.add("flash");
          set(r, "s-fail", "rejected", item.title, "assert failed · not lowercased — caught", item.right);
          caught++; bump(); await sleep(950); r.classList.remove("flash");
          set(r, "s-run", "retry", item.title, "re-dispatched with the failure", item.right); await sleep(750);
          set(r, "s-done", "done", item.title, "slugify('Hello World')=='hello-world' · passed", item.right);
          ver++; bump();
        } else if (item.chip === "s-held") { set(r, item.chip, item.label, item.title, item.why, item.right); held++; bump(); }
        else { set(r, item.chip, item.label, item.title, item.why, item.right); ver++; bump(); }
        await sleep(500);
      }
      setTitle("Nothing needs you."); await sleep(2600); void run();
    }
    const io = new IntersectionObserver((es) => { if (es[0].isIntersecting) { io.disconnect(); void run(); } });
    io.observe(el);
    return () => { alive = false; io.disconnect(); };
  }, []);

  return { rowsRef, title, figs };
}

const FEATURES = [
  ["Verify", "Done is a claim, not a fact", "Every commitment carries the check that proves it, defined before work starts. A claim that fails its evidence never reaches you."],
  ["Budget", "Your attention is the constraint", "Work is dispatched only when you can review it. Twelve agent tasks nobody can check by Friday is debt, not throughput."],
  ["Speculate", "Waiting is optional", "When a decision only you can make blocks the plan, Conductor builds every plausible answer overnight. You choose; the winner is already verified."],
  ["Compress", "Nine questions become two", "Escalations are clustered by the uncertainty behind them and ranked by what each answer unblocks. You answer once."],
  ["Trust", "Agents earn a lighter check", "Verification depth is priced per worker from outcomes. Trust rises slowly and falls the moment a worker misses."],
  ["Hire", "You hire an agent, not configure one", "Agents join the roster beside people, on probation, and an agent can act for a person without ever exceeding their authority."],
];

export function Landing({ go }: { go: (path: string) => void }) {
  const { rowsRef, title, figs } = useStage();
  return (
    <div className="landing">
      <nav className="nav"><div className="wrap"><div className="row">
        <div className="brand"><span className="mark">C</span> Conductor</div>
        <div className="links">
          <button className="btn ghost" onClick={() => go("/app")}>Live demo</button>
          <button className="btn ghost" onClick={() => go("/signup")}>Sign in</button>
          <button className="btn primary" onClick={() => go("/signup")}>Get started</button>
        </div>
      </div></div></nav>

      <header className="hero"><div className="glow" /><div className="wrap">
        <h1>The project manager for humans and agents.</h1>
        <p className="sub">Agents made work cheap and parallel. They also lie — confidently reporting done
          on work that is plausible and wrong. Conductor verifies every claim, budgets your attention,
          and builds every plausible answer while you sleep.</p>
        <div className="cta">
          <button className="btn primary" onClick={() => go("/signup")}>Start free</button>
          <button className="btn" onClick={() => go("/app")}>Open the live demo →</button>
        </div>
        <div className="trust">No card. The demo runs on synthetic data, no sign-in needed.</div>
      </div></header>

      <section className="framewrap"><div className="wrap">
        <div className="frame">
          <div className="bar"><i /><i /><i /><span className="livedot" /><span className="livelabel">loop running</span></div>
          <div className="stage">
            <div className="stage-head">
              <div className="stage-title">{title}</div>
              <div className="stage-figs">
                <div className="sf"><b className="fail">{figs.caught}</b><span>caught wrong</span></div>
                <div className="sf"><b>{figs.ver}</b><span>verified</span></div>
                <div className="sf"><b className="held">{figs.held}</b><span>held</span></div>
              </div>
            </div>
            <div className="stage-rows" ref={rowsRef} />
          </div>
        </div>
      </div></section>

      <section className="claim"><div className="wrap">
        <h2>Every tool assumes labour is expensive and judgment is free.<br /><span className="em">Agents inverted that.</span></h2>
        <p>The bottleneck is no longer doing the work. It is confirming the work is real. Conductor is built
          around the one resource that stayed scarce: your attention.</p>
      </div></section>

      <section className="wrap"><div className="feats">
        {FEATURES.map(([k, h, p]) => (
          <div className="feat" key={k}><div className="k">{k}</div><h3>{h}</h3><p>{p}</p></div>
        ))}
      </div></section>

      <section className="wrap"><div className="metrics">
        <div className="metric fail"><div className="n">3</div><div className="l">Claims caught before you saw them</div></div>
        <div className="metric"><div className="n">$0.24</div><div className="l">Spent building answers overnight</div></div>
        <div className="metric pass"><div className="n">1</div><div className="l">Question that actually needed you</div></div>
      </div></section>

      <section className="close"><div className="wrap">
        <h2>Stop paying people to check machines.</h2>
        <p>Conductor runs the loop and surfaces only the decisions that need a human.</p>
        <div className="cta">
          <button className="btn primary" onClick={() => go("/signup")}>Get started</button>
          <button className="btn" onClick={() => go("/app")}>Open the live demo →</button>
        </div>
      </div></section>

      <footer><div className="wrap" style={{ display: "flex", justifyContent: "space-between", width: "100%", flexWrap: "wrap", gap: 12 }}>
        <span>Conductor</span><span className="mono">humans + agents, one team</span>
      </div></footer>
    </div>
  );
}
