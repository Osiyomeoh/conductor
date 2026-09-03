import { useEffect, useRef, useState } from "react";
import "./landing.css";
import { Glyph } from "./logo";

type Row = { chip: string; label: string; title: string; why: string; right: string };
const SCRIPT: Row[] = [
  { chip: "s-done", label: "done", title: "Fix the payment webhook retry", why: "grep -q RETRY_OK webhook.txt · passed", right: "impl-agent" },
  { chip: "s-held", label: "held", title: "Migrate the onboarding events table", why: "reviewer has 0m left · waiting", right: "25m" },
  { chip: "bad", label: "", title: "Implement slugify(text)", why: "", right: "impl-agent" },
  { chip: "s-done", label: "done", title: "Competitive research on three tools", why: "research.txt · passed", right: "research-agent" },
];

// The self-running mini control room, the loop catching a bad claim.
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
          set(r, "s-fail", "rejected", item.title, "assert failed · not lowercased, caught", item.right);
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

export function Landing({ go }: { go: (path: string) => void }) {
  const { rowsRef, title, figs } = useStage();
  return (
    <div className="landing">
      <nav className="nav"><div className="wrap"><div className="row">
        <div className="brand"><span className="mark"><span className="glyph"><Glyph /></span></span> Conductor</div>
        <div className="navmenu">
          <div className="item">
            <button>Product <svg className="caret" viewBox="0 0 12 12"><path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.4" fill="none" /></svg></button>
            <div className="dropdown">
              {[["✓", "Verification", "Every claim meets its check before it is believed"],
                ["⑂", "Speculation", "Build every plausible answer while a decision waits"],
                ["◷", "Attention budget", "Dispatch only what a reviewer can absorb"],
                ["◐", "The roster", "Hire agents that earn trust like teammates"]].map(([ic, t, d]) => (
                <div className="di" key={t} onClick={() => go("/app")}>
                  <span className="ic">{ic}</span><div><div className="dt">{t}</div><div className="dd">{d}</div></div>
                </div>
              ))}
            </div>
          </div>
          <div className="item"><button onClick={() => go("/app")}>Customers</button></div>
          <div className="item"><button onClick={() => go("/signup")}>Pricing</button></div>
          <div className="item"><button onClick={() => go("/app")}>Now</button></div>
          <div className="item"><button onClick={() => go("/signup")}>Contact</button></div>
        </div>
        <div className="links">
          <button className="btn ghost" onClick={() => go("/signup")}>Sign in</button>
          <button className="btn primary" onClick={() => go("/signup")}>Get started</button>
        </div>
      </div></div></nav>

      <header className="hero"><div className="glow" /><div className="wrap">
        <h1>From one conversation to a team that runs itself.</h1>
        <p className="sub">Describe a sprint once. Conductor turns it into a working team of people and agents, dispatches the work, verifies every result, and tracks all of it. The best project manager you will ever have, and it only comes back to you when a real decision is waiting.</p>
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

      {/* Demonstrations, not an adjective list, each section shows the mechanism working. */}
      <section className="wrap"><div className="demo">
        <div className="head">
          <h2>Every claim meets its check.</h2>
          <div className="desc">An agent reports done, confidently, on work that is plausible and wrong.
            Conductor runs the evidence before it believes the claim, and the failure never reaches you.</div>
        </div>
        <div className="art">
          <div className="abar"><i /><i /><i /><span className="lbl">board</span></div>
          <div className="abody">
            <div className="arow"><span className="achip a-done">done</span>
              <div><div className="at">Fix the payment webhook retry</div><div className="aw">verified: pytest tests/test_webhook_retry.py · passed</div></div>
              <span className="aright">impl-agent</span></div>
            <div className="arow wash"><span className="achip a-fail">rejected</span>
              <div><div className="at">Implement slugify(text)</div><div className="aw">assert failed · 'Hello-World' is not 'hello-world', caught before review</div></div>
              <span className="aright">impl-agent</span></div>
            <div className="arow"><span className="achip a-run">retry</span>
              <div><div className="at">Implement slugify(text)</div><div className="aw">re-dispatched with the failure as context</div></div>
              <span className="aright">impl-agent</span></div>
            <div className="arow"><span className="achip a-done">done</span>
              <div><div className="at">Implement slugify(text)</div><div className="aw">verified: slugify('Hello World') == 'hello-world' · merged</div></div>
              <span className="aright">impl-agent</span></div>
          </div>
        </div>
      </div></section>

      <section className="wrap"><div className="demo">
        <div className="head">
          <h2>Waiting is optional.</h2>
          <div className="desc">When a decision only you can make blocks the plan, Conductor forks it across every
            plausible answer and builds them all overnight. You choose once; the winner is already verified.</div>
        </div>
        <div className="art">
          <div className="abar"><i /><i /><i /><span className="lbl">decision · onboarding paywall</span></div>
          <div className="abody">
            <div className="abranches">
              <div className="abr chosen"><div className="bo">after first value</div><div className="bc">$0.0854</div><div className="bs">merged, already verified</div></div>
              <div className="abr"><div className="bo">on signup</div><div className="bc">$0.0816</div><div className="bs">built · discarded</div></div>
              <div className="abr"><div className="bo">usage limit</div><div className="bc">$0.0000</div><div className="bs">built · discarded</div></div>
            </div>
            <div className="aspec-cap">Three branches built while the question was open. You answered in 20 seconds; the work was already done.</div>
          </div>
        </div>
      </div></section>

      <section className="wrap"><div className="demo">
        <div className="head">
          <h2>You hire an agent, not configure one.</h2>
          <div className="desc">Agents join the roster beside people, on probation, and earn a lighter check as
            they prove out. An agent can act for a person, inheriting their authority, never exceeding it.</div>
        </div>
        <div className="art">
          <div className="abar"><i /><i /><i /><span className="lbl">team</span></div>
          <div className="abody">
            <div className="mrow2"><div><div className="mn">Sam <span className="mkind">human</span></div><div className="mp">Product judgment and review · 150m review budget</div></div><span className="mstatus human">human</span></div>
            <div className="mrow2"><div><div className="mn">impl-agent <span className="mkind agent">agent</span></div><div className="mp">Writes and fixes application code · code 80% (4/5)</div></div><span className="mstatus probation">probation</span></div>
            <div className="mrow2"><div><div className="mn">research-agent <span className="mkind agent">agent</span></div><div className="mp">Competitive and technical research · research 67% (2/3)</div></div><span className="mstatus trusted">trusted</span></div>
            <div className="mrow2 delegate"><div><div className="mn">sam's delegate <span className="mkind agent">agent</span></div><div className="mp">Acts for Sam · inherits Sam's scopes, reviewed by Sam</div></div><span className="mstatus probation">probation</span></div>
          </div>
        </div>
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

      <footer className="foot-menu"><div className="wrap">
        <div className="cols">
          <div className="brandcol">
            <div className="b"><span className="mark"><span className="glyph"><Glyph /></span></span> Conductor</div>
            <p>The project manager for humans and agents. Verify every claim, budget your attention.</p>
          </div>
          <div className="col"><h5>Product</h5>
            <a onClick={() => go("/app")}>Verification</a><a onClick={() => go("/app")}>Speculation</a>
            <a onClick={() => go("/app")}>Attention budget</a><a onClick={() => go("/app")}>The roster</a></div>
          <div className="col"><h5>Company</h5>
            <a onClick={() => go("/app")}>Customers</a><a onClick={() => go("/signup")}>Pricing</a>
            <a onClick={() => go("/app")}>Now</a><a onClick={() => go("/signup")}>Contact</a></div>
          <div className="col"><h5>Resources</h5>
            <a onClick={() => go("/app")}>Live demo</a>
            <a href="https://strandsagents.com" target="_blank" rel="noreferrer">Strands Agents</a>
            <a href="https://github.com/Osiyomeoh/conductor" target="_blank" rel="noreferrer">GitHub</a>
            <a onClick={() => go("/signup")}>Documentation</a></div>
          <div className="col"><h5>Connect</h5>
            <a href="https://github.com/Osiyomeoh/conductor" target="_blank" rel="noreferrer">GitHub</a>
            <a onClick={() => go("/signup")}>Contact us</a><a onClick={() => go("/app")}>Community</a></div>
        </div>
        <div className="foot-bottom">
          <span>© 2026 Conductor</span>
          <span className="mono">Built on Strands Agents · Amazon Bedrock</span>
        </div>
      </div></footer>
    </div>
  );
}
