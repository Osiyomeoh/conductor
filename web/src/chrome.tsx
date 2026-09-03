import { Glyph } from "./logo";

// Shared marketing chrome: the public nav and footer used by the landing and
// every marketing page (Product, Customers, Pricing, Now, Contact). These
// pages are public; none of them enter the app.
export function MarketingNav({ go }: { go: (p: string) => void }) {
  return (
    <nav className="nav"><div className="wrap"><div className="row">
      <div className="brand" onClick={() => go("/")} style={{ cursor: "pointer" }}>
        <span className="mark"><span className="glyph"><Glyph /></span></span> Conductor
      </div>
      <div className="navmenu">
        <div className="item">
          <button onClick={() => go("/product")}>Product <svg className="caret" viewBox="0 0 12 12"><path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.4" fill="none" /></svg></button>
          <div className="dropdown">
            {[["✓", "Verification", "Every claim meets its check before it is believed"],
              ["⑂", "Speculation", "Build every plausible answer while a decision waits"],
              ["◷", "Attention budget", "Dispatch only what a reviewer can absorb"],
              ["◐", "The roster", "Hire agents that earn trust like teammates"]].map(([ic, t, d]) => (
              <div className="di" key={t} onClick={() => go("/product")}>
                <span className="ic">{ic}</span><div><div className="dt">{t}</div><div className="dd">{d}</div></div>
              </div>
            ))}
          </div>
        </div>
        <div className="item"><button onClick={() => go("/customers")}>Customers</button></div>
        <div className="item"><button onClick={() => go("/pricing")}>Pricing</button></div>
        <div className="item"><button onClick={() => go("/now")}>Now</button></div>
        <div className="item"><button onClick={() => go("/contact")}>Contact</button></div>
      </div>
      <div className="links">
        <button className="btn ghost" onClick={() => go("/signup")}>Sign in</button>
        <button className="btn primary" onClick={() => go("/signup")}>Get started</button>
      </div>
    </div></div></nav>
  );
}

export function MarketingFooter({ go }: { go: (p: string) => void }) {
  return (
    <footer className="foot-menu"><div className="wrap">
      <div className="cols">
        <div className="brandcol">
          <div className="b"><span className="mark"><span className="glyph"><Glyph /></span></span> Conductor</div>
          <p>The project manager for humans and agents. Verify every claim, budget your attention.</p>
        </div>
        <div className="col"><h5>Product</h5>
          <a onClick={() => go("/product")}>Overview</a><a onClick={() => go("/product")}>Verification</a>
          <a onClick={() => go("/product")}>Speculation</a><a onClick={() => go("/product")}>The roster</a></div>
        <div className="col"><h5>Company</h5>
          <a onClick={() => go("/customers")}>Customers</a><a onClick={() => go("/pricing")}>Pricing</a>
          <a onClick={() => go("/now")}>Now</a><a onClick={() => go("/contact")}>Contact</a></div>
        <div className="col"><h5>Resources</h5>
          <a onClick={() => go("/app")}>Live demo</a>
          <a href="https://strandsagents.com" target="_blank" rel="noreferrer">Strands Agents</a>
          <a href="https://github.com/Osiyomeoh/conductor" target="_blank" rel="noreferrer">GitHub</a></div>
        <div className="col"><h5>Connect</h5>
          <a href="https://github.com/Osiyomeoh/conductor" target="_blank" rel="noreferrer">GitHub</a>
          <a onClick={() => go("/contact")}>Contact us</a></div>
      </div>
      <div className="foot-bottom">
        <span>© 2026 Conductor</span>
        <span className="mono">Built on Strands Agents · Amazon Bedrock</span>
      </div>
    </div></footer>
  );
}
