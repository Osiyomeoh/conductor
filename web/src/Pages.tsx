import "./landing.css";
import "./pages.css";
import { MarketingFooter, MarketingNav } from "./chrome";

function Shell({ go, children }: { go: (p: string) => void; children: React.ReactNode }) {
  return <div className="landing"><MarketingNav go={go} /><main className="page">{children}</main><MarketingFooter go={go} /></div>;
}
function PageHero({ eyebrow, title, lede }: { eyebrow: string; title: string; lede: string }) {
  return <header className="page-hero"><div className="wrap">
    <div className="peyebrow">{eyebrow}</div><h1>{title}</h1><p className="plede">{lede}</p>
  </div></header>;
}

export function ProductPage({ go }: { go: (p: string) => void }) {
  const feats: [string, string, string][] = [
    ["Verification", "Done is a claim, not a fact", "Every commitment carries the check that proves it, written before work starts. A claim that fails its evidence is caught and re-dispatched before it ever reaches a human."],
    ["Attention budget", "Your review time is the constraint", "Work is dispatched only when a reviewer can absorb it. Twelve agent tasks nobody can check by Friday is debt, not throughput, so Conductor holds them back and says why."],
    ["Speculation", "Waiting is optional", "When a decision only a person can make blocks the plan, Conductor forks it across every plausible answer and builds them all overnight. You choose once; the winner is already verified."],
    ["The roster", "Hire an agent, do not configure one", "Agents join the roster beside people, on probation, and earn a lighter check as they prove out. An agent can act for a person, inheriting their authority and never exceeding it."],
  ];
  return <Shell go={go}>
    <PageHero eyebrow="Product" title="One loop. Humans and agents. Fully tracked."
      lede="Conductor decomposes a sprint, dispatches the work to people and agents, verifies every result against a real check, and surfaces only when a decision needs you." />
    <section className="wrap"><div className="prows">
      {feats.map(([k, h, p]) => (
        <div className="prow-feat" key={k}><div className="pk">{k}</div><div><h3>{h}</h3><p>{p}</p></div></div>
      ))}
    </div>
      <div className="page-cta"><button className="btn primary" onClick={() => go("/app")}>Open the live demo →</button></div>
    </section>
  </Shell>;
}

export function CustomersPage({ go }: { go: (p: string) => void }) {
  return <Shell go={go}>
    <PageHero eyebrow="Who it is for" title="For anyone who now supervises agents."
      lede="The moment you add AI agents to a team, output goes up and a new problem appears: an agent reports done, confidently, on work that is wrong. Conductor is for the person who has to catch that." />
    <section className="wrap"><div className="who">
      {[["The engineer lead", "You dispatch tasks to coding agents all day. Conductor runs the checks so you review verified work, not confident guesses."],
        ["The solo founder", "You are the whole team and the reviewer. Conductor budgets your attention and only pulls you in for a real decision."],
        ["The small studio", "A few people, many agents. Conductor keeps the roster honest: trust is earned per worker, per kind of work."]].map(([t, d]) => (
        <div className="whocard" key={t}><h3>{t}</h3><p>{d}</p></div>
      ))}
    </div></section>
  </Shell>;
}

export function PricingPage({ go }: { go: (p: string) => void }) {
  return <Shell go={go}>
    <PageHero eyebrow="Pricing" title="Pay for work that passed its check."
      lede="Rejected agent output is free, because you should never pay for work that was wrong. A platform fee per person, plus a rate on each verified commitment." />
    <section className="wrap"><div className="tiers">
      {[["Solo", "$0", "For one person and their agents", ["The full loop on your own repo", "Deterministic demo, no card", "Community support"], "Start free", "/signup"],
        ["Team", "$30", "per person / month, plus usage", ["Everything in Solo", "Per verified commitment metering", "Durable multi-tenant state", "Priority support"], "Get started", "/signup"],
        ["Scale", "Talk to us", "For studios running many agents", ["Volume pricing on verified work", "AgentCore deployment", "SSO and audit", "Dedicated support"], "Contact", "/contact"]].map(([name, price, sub, feats, cta, to]) => (
        <div className="tier" key={name as string}>
          <div className="tname">{name}</div><div className="tprice">{price}</div><div className="tsub">{sub}</div>
          <ul>{(feats as string[]).map((f) => <li key={f}>{f}</li>)}</ul>
          <button className="btn primary" onClick={() => go(to as string)}>{cta}</button>
        </div>
      ))}
    </div>
      <p className="pricing-note">Two numbers matter more than the total: cost per verified commitment, which is what you got, and spend on rejected claims, which is what the verification layer saved you from reviewing by hand.</p>
    </section>
  </Shell>;
}

export function NowPage({ go }: { go: (p: string) => void }) {
  const log: [string, string, string][] = [
    ["Sep 3, 2026", "React and TypeScript app", "The whole product is now one React and TypeScript single-page app, with a typed client against the API."],
    ["Sep 3, 2026", "Real git execution", "Agent work runs in real git worktrees. Nothing merges to the base branch until its evidence passes."],
    ["Sep 2, 2026", "Speculation engine", "Conductor now builds every plausible answer to an open decision while it waits, and merges the one you choose."],
    ["Sep 1, 2026", "Durable multi-tenant state", "Every run is event-sourced. A restart resumes the work and the trust the previous process left."],
  ];
  return <Shell go={go}>
    <PageHero eyebrow="Now" title="What we shipped recently." lede="Conductor is built in the open. Here is what changed." />
    <section className="wrap"><div className="changelog">
      {log.map(([date, t, d]) => (
        <div className="clrow" key={t}><div className="cldate">{date}</div><div><h3>{t}</h3><p>{d}</p></div></div>
      ))}
    </div></section>
  </Shell>;
}

export function ContactPage({ go }: { go: (p: string) => void }) {
  return <Shell go={go}>
    <PageHero eyebrow="Contact" title="Let us know what you are building."
      lede="Questions, a demo for your team, or a problem you want an agent workforce to take on. We read everything." />
    <section className="wrap"><div className="contact">
      <form className="cform" onSubmit={(e) => { e.preventDefault(); alert("Prototype form. Nothing was sent."); }}>
        <div className="cf"><label>Name</label><input placeholder="Your name" /></div>
        <div className="cf"><label>Work email</label><input type="email" placeholder="you@team.com" /></div>
        <div className="cf"><label>What can we help with?</label><textarea rows={4} placeholder="Tell us about your team and your agents." /></div>
        <button className="btn primary" type="submit">Send</button>
        <div className="cnote">Prototype form. It collects nothing and sends nothing.</div>
      </form>
      <div className="cside">
        <h4>Other ways</h4>
        <a href="https://github.com/Osiyomeoh/conductor" target="_blank" rel="noreferrer">GitHub</a>
        <a onClick={() => go("/app")}>Open the live demo</a>
        <a onClick={() => go("/pricing")}>Pricing</a>
      </div>
    </div></section>
  </Shell>;
}
