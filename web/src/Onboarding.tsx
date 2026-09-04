import { useState } from "react";
import "./onboarding.css";
import { Glyph } from "./logo";

function Toggle() {
  const [on, setOn] = useState(true);
  return <div className={`sw ${on ? "on" : ""}`} onClick={() => setOn((v) => !v)}><i /></div>;
}

export function Onboarding({ go }: { go: (path: string) => void }) {
  const [i, setI] = useState(0);
  const N = 5;
  const finish = i === N - 1;
  const next = () => { if (finish) go("/app"); else setI((x) => x + 1); };

  const steps = [
    { title: "Create your workspace", lede: "A quick walkthrough of the demo. Nothing here signs you up; your board is created the moment you enter.", primary: "Create workspace", skip: false,
      body: <>
        <div className="field"><label>Workspace name</label><input className="input" placeholder="Acme" /></div>
        <div className="field"><label>Workspace URL</label><div className="urlrow"><span className="pfx">conductor.app/</span><input placeholder="acme" /></div></div>
        <div className="rowfields"><div className="field"><label>Region</label><select className="select"><option>United States</option><option>European Union</option></select></div></div>
      </> },
    { title: "Set up your profile", lede: "How you appear to your team and to the agents you supervise.", primary: "Continue", skip: true,
      body: <>
        <div className="field"><label>Full name</label><input className="input" placeholder="Samuel Aleonomoh" /></div>
        <div className="field"><label>Title</label><input className="input" placeholder="Founder" /></div>
      </> },
    { title: "Invite your team", lede: "Humans and agents work side by side. Bring the humans first.", primary: "Send invitations", skip: true,
      body: <>
        <div className="field"><label>Email addresses</label><input className="input" placeholder="you@team.com, teammate@team.com" /></div>
        <div className="foot">You can also share a link. Agents are added later, from the roster.</div>
      </> },
    { title: "Connect your repository", lede: "Agents do real work in real branches. Conductor merges only what passes its checks.", primary: "Continue", skip: true,
      body: <>
        <div className="connect">
          <div className="crow"><h4>Real execution</h4><p>Each task runs in its own git worktree.</p></div>
          <div className="crow"><h4>Verified merges</h4><p>Nothing reaches your base branch on a worker's word.</p></div>
          <div className="crow"><h4>Trust that compounds</h4><p>Agents earn a lighter check as they prove out.</p></div>
        </div>
        <div className="foot">In the live app this connects a real repo (gated behind a flag, local only). The demo runs on an isolated sandbox.</div>
      </> },
    { title: "You're set.", lede: "Conductor runs the loop and surfaces only the decisions that need you. On a good day, it stays quiet.", primary: "Enter Conductor", skip: false,
      body: <>
        <div className="connect">
          <div className="crow toggle"><div><h4>Weekly digest</h4><p>What was verified, caught, and decided.</p></div><Toggle /></div>
          <div className="crow toggle"><div><h4>Escalation alerts</h4><p>Ping me the moment a real decision is waiting.</p></div><Toggle /></div>
        </div>
      </> },
  ];
  const s = steps[i];

  return (
    <div className="split">
      <div className="left">
        <div className="brand"><span className="mark"><span className="glyph"><Glyph /></span></span> Conductor</div>
        <div className="formwrap">
          <div className="step" key={i}>
            <h1>{s.title}</h1><p className="lede">{s.lede}</p>
            {s.body}
            <div className="actions">
              {s.skip && <button className="btn ghost" onClick={next}>Skip</button>}
              <button className="btn primary" onClick={next}>{s.primary}</button>
            </div>
          </div>
          <div className="dots">{steps.map((_, k) => <span key={k} className={`dot ${k === i ? "on" : k < i ? "done" : ""}`} />)}</div>
        </div>
      </div>
      <div className="right">
        <div className="glow" />
        <div className="preview"><div className="pcard">
          <div className="pbar"><i /><i /><i /><span className="plive"><span className="d" /> loop running</span></div>
          <div className="pbody">
            <div className="ptitle">{finish ? "Nothing needs you." : "One thing needs you."}</div>
            <div className="pfigs">
              <div className="pf fail"><b>3</b><span>caught wrong</span></div>
              <div className="pf"><b>6</b><span>verified</span></div>
              <div className="pf held"><b>1</b><span>held</span></div>
            </div>
            <div className="prow"><span className="pchip pc-done">done</span><div><div className="pt">Fix the payment webhook retry</div><div className="pw">grep -q RETRY_OK webhook.txt · passed</div></div></div>
            <div className="prow"><span className="pchip pc-fail">rejected</span><div><div className="pt">Implement slugify(text)</div><div className="pw">not lowercased, caught, re-dispatched</div></div></div>
            <div className="prow"><span className="pchip pc-held">held</span><div><div className="pt">Migrate the onboarding events table</div><div className="pw">reviewer has 0m left · waiting</div></div></div>
          </div>
        </div></div>
      </div>
    </div>
  );
}
