import { useEffect, useState } from "react";
import { api } from "./api";
import type { State, DecisionSummary, DecisionDetail, Team, Plan, Activity } from "./types";
import { useCount, useDictation } from "./hooks";

const esc = (s: unknown) => String(s ?? "");

export function Figure({ cls, value }: { cls: string; value: number | string }) {
  const numeric = typeof value === "number";
  const n = useCount(numeric ? (value as number) : 0);
  return <div className={`fig ${cls}`}><div className="n">{numeric ? n : value}</div>{/* label set by caller */}</div>;
}

function DecisionCard({ d, onOpen, onAnswer }: {
  d: DecisionSummary; onOpen: (id: string) => void;
  onAnswer: (id: string, choice: string) => void;
}) {
  return (
    <div className="card decision" onClick={() => onOpen(d.id)}>
      <div className="q">{d.question}</div>
      <div className="meta">
        unblocks <b>{d.commitments || d.unblocks}</b> commitment{(d.commitments || d.unblocks) === 1 ? "" : "s"}
        {d.review_minutes > 0 && <> · frees <b>{d.review_minutes >= 60 ? `~${(d.review_minutes / 60).toFixed(1)}h` : `${d.review_minutes}m`}</b> of your review</>}
        {d.compressed_from > 1 && <> · compressed from <b>{d.compressed_from}</b> escalations</>}
        {d.branches > 0 && <> · <b>{d.prebuilt}</b> of {d.branches} branches already built · ${d.spent.toFixed(4)} spent</>}
      </div>
      {d.needs_framing ? (
        <div className="note">No options yet. This one needs framing before anyone can answer it.</div>
      ) : (
        <div className="opts">
          {d.options.map((o) => (
            <button key={o} onClick={(e) => { e.stopPropagation(); onAnswer(d.id, o); }}>{o}</button>
          ))}
          {d.branches > 0 && (
            <button className="see" onClick={(e) => { e.stopPropagation(); onOpen(d.id); }}>See the branches →</button>
          )}
        </div>
      )}
    </div>
  );
}

export function HomeView({ s, onOpen, onAnswer, onPlan }: {
  s: State; onOpen: (id: string) => void;
  onAnswer: (id: string, choice: string) => void; onPlan: () => void;
}) {
  const n = s.decisions.length;
  const title = n === 0 ? "Nothing needs you." : n === 1 ? "One thing needs you." : `${n} things need you.`;
  const att = s.attention[0] ?? { spent: 0 };
  const figs = n === 0
    ? [["ink", s.metrics.verified, "Verified this run"], ["pass", 0, "Things need you"], ["held", s.in_flight, "In flight now"]] as const
    : [["fail", s.metrics.claims_rejected, "Claims caught before you saw them"],
       ["ink", `$${s.cost.discarded.toFixed(2)}`, "Spent building answers overnight"],
       ["held", att.spent, "Attention spent today"]] as const;
  return (
    <>
      <Head title={title} sub={s.compression}
        actions={<><button className="b" onClick={() => location.assign("/app#board")}>Open board</button>
          <button className="b primary" onClick={onPlan}>Plan a sprint</button></>} />
      <div className="vbody"><div className="vwrap">
        <div className="hero"><div className="figures">
          {figs.map(([cls, val, label]) => (
            <div className={`fig ${cls}`} key={label}>
              <FigNum value={val} /><div className="l">{label}</div>
            </div>
          ))}
        </div></div>
        <div className="section"><div className="label">Needs you</div>
          {n === 0 ? (
            <div className="card decision empty"><div className="run2">The loop is running.</div>
              <div className="sub">Verifying, recovering and dispatching. You will hear from it when there is a judgment call.</div></div>
          ) : s.decisions.map((d) => <DecisionCard key={d.id} d={d} onOpen={onOpen} onAnswer={onAnswer} />)}
        </div>
        <div className="section"><div className="label">Recent activity</div>
          <div className="card log">{s.events.slice(0, 14).map((e, i) => <div key={i}>{e}</div>)}</div></div>
      </div></div>
    </>
  );
}

function FigNum({ value }: { value: number | string }) {
  const numeric = typeof value === "number";
  const n = useCount(numeric ? (value as number) : 0);
  return <div className="n">{numeric ? n : value}</div>;
}

export function BoardView({ s, onTick }: { s: State; onTick: (n: number) => void }) {
  return (<>
    <Head title="Board" sub={`${s.board.length} commitments`}
      actions={<button className="b" onClick={() => onTick(6)}>Run six</button>} />
    <div className="vbody"><div className="vwrap"><div className="card">
      {s.board.map((x) => (
        <div className={`row ${x.status === "rejected" ? "fail" : ""}`} key={x.id}>
          <span className={`chip c-${x.status}`}>{x.status.replace("_", " ")}</span>
          <div><span className="t">{x.title}</span>{x.speculative && <span className="spec">SPEC</span>}
            <div className="why">{x.reason}</div></div>
          <span className="who">{x.owner ?? ""}</span><span className="cost">{x.review_cost}m</span>
        </div>
      ))}
    </div></div></div>
  </>);
}

export function DecisionsView({ s, onOpen, onAnswer }: {
  s: State; onOpen: (id: string) => void; onAnswer: (id: string, choice: string) => void;
}) {
  return (<>
    <Head title="Decisions" sub={s.compression} />
    <div className="vbody"><div className="vwrap"><div className="section">
      <div className="label">Open</div>
      {s.decisions.length ? s.decisions.map((d) => <DecisionCard key={d.id} d={d} onOpen={onOpen} onAnswer={onAnswer} />)
        : <div className="card decision empty"><div className="run2">No open decisions.</div>
            <div className="sub">The loop only surfaces a question when a human's judgment is genuinely required.</div></div>}
    </div></div></div>
  </>);
}

export function CostView({ s }: { s: State }) {
  const c = s.cost;
  return (<>
    <Head title="Cost & trust" sub={`$${c.per_verified.toFixed(4)} per verified item`} />
    <div className="vbody"><div className="vwrap"><div className="grid2">
      <div className="card panel"><div className="label">Cost</div>
        <div className="kv cost-row"><span>on work that passed</span><b className="pass">${c.verified.toFixed(4)}</b></div>
        <div className="kv cost-row"><span>on claims that failed</span><b className="fail">${c.rejected.toFixed(4)}</b></div>
        <div className="kv cost-row"><span>on discarded branches</span><b>${c.discarded.toFixed(4)}</b></div>
        <div className="kv cost-row total"><span>per verified item</span><b>${c.per_verified.toFixed(4)}</b></div>
        <div className="note">Failed claims were never reviewed by a person.</div></div>
      <div className="card panel"><div className="label">Attention</div>
        {s.attention.map((a) => {
          const used = a.total ? Math.round(((a.spent + a.committed) / a.total) * 100) : 0;
          return <div key={a.reviewer}>
            <div className="kv"><span>{a.reviewer}</span><b>{a.remaining}m free</b></div>
            <div className="bar"><i style={{ width: `${used}%` }} /></div>
            <div className="note">{a.spent}m spent · {a.committed}m in flight · {a.total}m budget</div></div>;
        })}</div>
      <div className="card panel" style={{ gridColumn: "1 / -1" }}><div className="label">Trust</div>
        {s.trust.map((t) => {
          const cls = t.type !== "agent" ? "t-human" : t.probation ? "t-probation" : "t-trusted";
          const lab = t.type !== "agent" ? "human" : t.probation ? "probation" : "trusted";
          return <div className="trow" key={t.worker}><div className="thead">
            <span className="who">{t.worker}{t.principal && <small style={{ color: "var(--t3)" }}> for {t.principal}</small>}</span>
            <span className={`tpill ${cls}`}>{lab}</span></div>
            {t.detail && !t.detail.includes("no history") && <div className="tdetail">{t.detail}</div>}</div>;
        })}</div>
    </div></div></div>
  </>);
}

export function ActivityView() {
  const [a, setA] = useState<Activity | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => { void api.activity().then((x) => { if (alive) setA(x); }); };
    load(); const t = setInterval(load, 4000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  if (!a) return <><Head title="Activity" sub="loading" /><div className="vbody" /></>;
  const workers = Object.entries(a.by_worker);
  return (<>
    <Head title="Activity" sub="every action, attributed, from the durable event log" />
    <div className="vbody"><div className="vwrap">
      {workers.length > 0 && (
        <div className="actbar">
          {workers.map(([w, s]) => (
            <div className="actworker" key={w}>
              <span className="aw-name">{w}</span>
              <span className="aw-stat pass">{s.verified} verified</span>
              {s.caught > 0 && <span className="aw-stat fail">{s.caught} caught</span>}
            </div>
          ))}
        </div>
      )}
      <div className="stream">
        {a.events.map((e) => (
          <div className={`sitem tone-${e.tone}`} key={e.seq}>
            <span className="sdot" />
            <span className="stime mono">{e.at}</span>
            <div className="sbody">
              <span className="sactor">{e.actor ?? "conductor"}</span>{" "}
              <span className="sverb">{e.verb}</span>{" "}
              {e.title && <span className="stitle2">{e.title}</span>}
              {e.detail && <div className="sdetail mono">{e.detail}</div>}
            </div>
          </div>
        ))}
        {a.events.length === 0 && <div className="note" style={{ padding: 20 }}>No activity yet. Plan a sprint and run the loop.</div>}
      </div>
    </div></div>
  </>);
}

export function RealView() {
  const [s, setS] = useState<import("./types").RealState | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  useEffect(() => { void api.realState().then(setS).catch(() => {}); }, []);

  const run = async () => {
    setBusy(true);
    try { setS(await api.realRun(8, live)); } finally { setBusy(false); }
  };
  const reset = async () => {
    setBusy(true);
    try { setS(await api.realReset(live)); } finally { setBusy(false); }
  };

  const m = s?.metrics;
  return (<>
    <Head title="Real execution" sub="real git worktrees · real checks · only verified code merges"
      actions={<>
        <label className="livetog"><input type="checkbox" checked={live}
          onChange={(e) => setLive(e.target.checked)} /> live agent</label>
        <button className="b" onClick={() => void reset()} disabled={busy}>Reset</button>
        <button className="b primary" onClick={() => void run()} disabled={busy}>
          {busy ? "Running…" : "Run on a real repo"}</button>
      </>} />
    <div className="vbody"><div className="vwrap">
      <div className="realnote">
        Every task runs in its own git worktree off the base branch. The check runs
        as a real command inside that worktree. A pass merges; a failure is discarded
        and re-dispatched. {live ? "The code is written by a live Strands agent." : "Turn on ‘live agent’ to have a Strands agent write the code; off, a deterministic worker plants a confident bug so you can watch it get caught."}
      </div>

      {m && (
        <div className="realfigs">
          <div className="fig fail"><div className="n">{m.claims_rejected}</div><div className="l">caught before merge</div></div>
          <div className="fig pass"><div className="n">{m.verified}</div><div className="l">verified &amp; merged</div></div>
          <div className="fig ink"><div className="n">{s?.in_flight ?? 0}</div><div className="l">in flight</div></div>
        </div>
      )}

      <div className="realgrid">
        <div className="section">
          <div className="label">Base branch history {s?.repo?.path && <span className="mono dim">· {s.repo.path}</span>}</div>
          <div className="gitlog card">
            {(s?.repo?.log ?? []).map((ln, i) => {
              const merge = ln.includes("conductor: merge");
              return <div className={`gitline ${merge ? "merge" : ""}`} key={i}>
                <span className="mono">{ln}</span></div>;
            })}
            {(!s?.repo?.log || s.repo.log.length === 0) &&
              <div className="note" style={{ padding: 16 }}>No commits yet. Run it.</div>}
          </div>
        </div>

        <div className="section">
          <div className="label">Verified code on the base <span className="dim">(only passing work is here)</span></div>
          {Object.entries(s?.repo?.files ?? {}).map(([name, body]) => (
            <div className="filecard card" key={name}>
              <div className="filename mono">{name}</div>
              <pre className="filebody mono">{body}</pre>
            </div>
          ))}
          {Object.keys(s?.repo?.files ?? {}).length === 0 &&
            <div className="card"><div className="note" style={{ padding: 16 }}>Nothing merged yet.</div></div>}
        </div>
      </div>
    </div></div>
  </>);
}

export function RepoView() {
  const [s, setS] = useState<import("./types").RepoConnect | null>(null);
  const [path, setPath] = useState("");
  const [task, setTask] = useState({ title: "", file: "", check: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { void api.repoStatus().then(setS).catch(() => {}); }, []);

  const guard = async (fn: () => Promise<import("./types").RepoConnect>) => {
    setBusy(true); setErr(null);
    try { setS(await fn()); }
    catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
    finally { setBusy(false); }
  };
  const connect = () => guard(() => api.repoConnect(path));
  const addTask = () => guard(async () => { const r = await api.repoTask(task); setTask({ title: "", file: "", check: "" }); return r; });
  const run = () => guard(() => api.repoRun(8));
  const disconnect = () => guard(() => api.repoDisconnect());

  if (!s) return <><Head title="Your repo" sub="loading" /><div className="vbody" /></>;

  if (!s.enabled) return (<>
    <Head title="Your repo" sub="connect a real repository you own" />
    <div className="vbody"><div className="vwrap">
      <div className="card lockcard">
        <div className="lockttl">Real-repo execution is off by default</div>
        <div className="lockbody">
          Connecting a repo lets Conductor run each task's check as a real command
          against your code. That is real code execution, so it is never enabled on
          the public demo. Turn it on deliberately, on your own machine:
          <pre className="mono lockpre">CONDUCTOR_ALLOW_REPO=1 CONDUCTOR_PROVIDER=gemini \
GEMINI_API_KEY=… python serve.py</pre>
          Then reload this page. Conductor writes into isolated git worktrees off
          your base branch and merges only what passes. It never pushes to a remote.
        </div>
      </div>
    </div></div>
  </>);

  const board = s.board ?? [];
  const m = s.metrics;
  return (<>
    <Head title="Your repo" sub={s.connected ? s.path ?? "" : "connect a real repository you own"}
      actions={s.connected
        ? <><button className="b" onClick={() => void disconnect()} disabled={busy}>Disconnect</button>
            <button className="b primary" onClick={() => void run()} disabled={busy || board.length === 0}>{busy ? "Running…" : "Run the loop"}</button></>
        : undefined} />
    <div className="vbody"><div className="vwrap">
      {err && <div className="card errcard">{err}</div>}

      {!s.connected ? (
        <div className="card connectcard">
          <div className="label">Connect a local git repository</div>
          <div className="connectrow">
            <input className="input mono" placeholder="/Users/you/code/my-project" value={path}
              onChange={(e) => setPath(e.target.value)} />
            <button className="b primary" onClick={() => void connect()} disabled={busy || !path.trim()}>Connect</button>
          </div>
          <div className="realnote" style={{ marginTop: 12 }}>
            A local path to a git repo. Conductor operates only in throwaway
            worktrees off your base branch and merges verified work into your local
            base. It never pushes.
          </div>
        </div>
      ) : (<>
        {s.live === false && <div className="card errcard">No live agent configured. Set CONDUCTOR_PROVIDER=gemini and GEMINI_API_KEY so the worker can write code.</div>}

        <div className="card taskcard">
          <div className="label">Add a task</div>
          <div className="taskgrid">
            <input className="input" placeholder="Task — e.g. Implement slugify(text)" value={task.title}
              onChange={(e) => setTask({ ...task, title: e.target.value })} />
            <input className="input mono" placeholder="target file — e.g. slugify.py" value={task.file}
              onChange={(e) => setTask({ ...task, file: e.target.value })} />
            <input className="input mono" placeholder="check command — e.g. python -c &quot;import slugify; assert slugify.slugify('A B')=='a-b'&quot;" value={task.check}
              onChange={(e) => setTask({ ...task, check: e.target.value })} />
            <button className="b" onClick={() => void addTask()}
              disabled={busy || !task.title.trim() || !task.file.trim() || !task.check.trim()}>Add task</button>
          </div>
          <div className="realnote" style={{ marginTop: 10 }}>
            The check command is your definition of done. The agent writes the file
            to satisfy it; the command runs for real; only a pass merges.
          </div>
        </div>

        {m && (
          <div className="realfigs">
            <div className="fig fail"><div className="n">{m.claims_rejected}</div><div className="l">caught before merge</div></div>
            <div className="fig pass"><div className="n">{m.verified}</div><div className="l">verified &amp; merged</div></div>
            <div className="fig ink"><div className="n">{s.in_flight ?? 0}</div><div className="l">in flight</div></div>
          </div>
        )}

        <div className="realgrid">
          <div className="section">
            <div className="label">Tasks</div>
            <div className="card">
              {board.length === 0 && <div className="note" style={{ padding: 16 }}>No tasks yet. Add one above.</div>}
              {board.map((x) => (
                <div className={`row ${x.status === "rejected" ? "fail" : ""}`} key={x.id}>
                  <span className={`chip c-${x.status}`}>{x.status.replace("_", " ")}</span>
                  <div><span className="t">{x.title}</span>
                    <div className="why mono">{x.evidence.spec}</div></div>
                  <span className="cost">{x.attempts > 0 ? `try ${x.attempts}` : ""}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="section">
            <div className="label">Base branch history</div>
            <div className="gitlog card">
              {(s.repo?.log ?? []).map((ln, i) => (
                <div className={`gitline ${ln.includes("conductor: merge") ? "merge" : ""}`} key={i}><span className="mono">{ln}</span></div>
              ))}
              {(!s.repo?.log || s.repo.log.length === 0) && <div className="note" style={{ padding: 16 }}>No commits from Conductor yet.</div>}
            </div>
          </div>
        </div>
      </>)}
    </div></div>
  </>);
}

export function TeamView() {
  const [t, setT] = useState<Team | null>(null);
  useEffect(() => { void api.team().then(setT); }, []);
  if (!t) return <><Head title="Team" sub="loading" /><div className="vbody" /></>;
  return (<>
    <Head title="Team" sub="humans and agents, one roster" />
    <div className="vbody"><div className="vwrap">
      {t.proposals.map((p) => (
        <div key={p.kind} className="card panel" style={{ border: "1px solid var(--held)", background: "var(--held-bg)", marginBottom: 24 }}>
          <div className="label" style={{ color: "var(--held)" }}>Hiring proposal</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{p.question}</div>
          <div className="opts" style={{ marginTop: 14 }}>{p.options.map((o) => <button className="b" key={o}>{o}</button>)}</div>
        </div>
      ))}
      <div className="card">
        {t.members.map((m) => {
          const cls = m.type !== "agent" ? "t-human" : m.probation ? "t-probation" : "t-trusted";
          const lab = m.type !== "agent" ? "human" : m.probation ? "probation" : "trusted";
          return (
            <div className="row" style={{ gridTemplateColumns: "1fr auto auto", paddingLeft: m.principal ? 32 : 18 }} key={m.id}>
              <div><div className="t">{m.name} <span className="spec">{m.type}</span></div>
                <div className="why">{m.purpose}{m.principal && <> · acts for {m.principal.replace("human_", "")}, inherits their scopes, reviewed by them</>}</div></div>
              <div className="mono" style={{ fontSize: 11, color: "var(--t2)", textAlign: "right", maxWidth: 300 }}>
                {m.skills.map((sk) => sk.score === null ? `${sk.kind} —` : `${sk.kind} ${Math.round(sk.score * 100)}% (${sk.passes}/${sk.total})`).join("  ")}</div>
              <span className={`tpill ${cls}`}>{lab}</span>
            </div>
          );
        })}
      </div>
      <div className="section" style={{ marginTop: 22, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
        <div className="label">Probation</div>
        <p style={{ color: "var(--t2)", fontSize: 13 }}>New teammates start with no trust. Everything they claim is deeply verified until they earn a lighter check. Graduation is on evidence, not time served.</p>
      </div>
    </div></div>
  </>);
}

export function Head({ title, sub, actions }: { title: string; sub?: string; actions?: React.ReactNode }) {
  return <header className="vhead"><div><h1>{esc(title)}</h1>{sub && <div className="sub">{sub}</div>}</div>
    <div className="actions">{actions}</div></header>;
}

// --- decision detail overlay (the signature screen) ---
export function DecisionOverlay({ id, onClose, onAnswer }: {
  id: string; onClose: () => void; onAnswer: (id: string, choice: string) => void;
}) {
  const [d, setD] = useState<DecisionDetail | null>(null);
  useEffect(() => { void api.decision(id).then(setD); }, [id]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  if (!d || d.error) return null;
  const n = d.branches.length;
  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet">
        <button className="close" onClick={onClose}>✕</button>
        <div className="d-q">{d.question}</div>
        <div className="d-id">{d.id}</div>
        <div className="d-meta">unblocks {d.unblocks} items · ${d.spent.toFixed(4)} spent building answers</div>
        {d.answer && <div className="answered">✓ answered — {d.answer}</div>}
        {n > 0 && <>
          <Diagram n={n} />
          <div className="dcap">Built while this question was open. Choosing an answer merges that branch immediately; the others are discarded. The waiting time was already spent doing the work.</div>
          <div className="branches">{d.branches.map((b) => (
            <div className={`branch ${b.chosen ? "chosen" : ""} ${b.discarded ? "discarded" : ""}`} key={b.option}>
              <div className="b-head"><div className="b-opt">{b.option}</div><div className="b-cost">${b.cost.toFixed(4)}</div></div>
              <div className={`b-state ${b.chosen ? "chosen" : ""}`}>
                {b.chosen ? "merged — already verified" : b.discarded ? "discarded when you chose" : `${b.verified}/${b.total} verified · waiting on your answer`}</div>
              {b.work.map((w, i) => (
                <div className="w" key={i}><span className="tick">{w.status === "done" ? "✓" : "·"}</span>
                  <div><div className="wt">{w.title}</div>{w.evidence && <div className="we">{w.evidence}</div>}</div></div>
              ))}
            </div>
          ))}</div>
        </>}
        {!d.answer && d.options.length >= 2 && (
          <div className="d-opts">{d.options.map((o) => (
            <button key={o} onClick={() => { onAnswer(d.id, o); onClose(); }}>{o}</button>))}</div>
        )}
      </div>
    </div>
  );
}

function Diagram({ n }: { n: number }) {
  const W = 560, H = Math.max(120, n * 74), x0 = 8, y0 = H / 2, x1 = W - 8;
  return (
    <div className="diagram"><svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet" aria-hidden>
      {Array.from({ length: n }).map((_, i) => {
        const y1 = n === 1 ? y0 : (H / (n + 1)) * (i + 1), br = i === 0;
        return <path key={i} d={`M${x0} ${y0} C ${W * .42} ${y0}, ${W * .5} ${y1}, ${x1} ${y1}`}
          fill="none" stroke={br ? "var(--line-strong)" : "var(--line)"} strokeWidth={br ? 1.6 : 1} />;
      })}
      <circle cx={x0} cy={y0} r={3.5} fill="var(--accent)" />
    </svg></div>
  );
}

// --- plan overlay ---
const DEFAULT_INTENT = "Next sprint I need the onboarding flow redesigned, the payment webhook fixed, and competitive research on three tools. Sarah owns design, agents can handle the research and the webhook tests.";

export function PlanOverlay({ onClose, onApproved }: { onClose: () => void; onApproved: () => void }) {
  const [intent, setIntent] = useState(DEFAULT_INTENT);
  const [interim, setInterim] = useState("");
  const [p, setP] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const dictation = useDictation(
    (phrase) => setIntent((prev) => (prev.trim() ? prev.trim() + " " : "") + phrase),
    (text) => setInterim(text));
  const mic = () => { if (dictation.listening) { dictation.stop(); setInterim(""); } else dictation.start(); };

  const generate = async () => { setBusy(true); try { setP(await api.plan(intent)); } finally { setBusy(false); } };
  const approve = async () => { setBusy(true); try { await api.approve(intent); onApproved(); onClose(); } finally { setBusy(false); } };

  const assignee = (c: Plan["commitments"][number]) =>
    c.judgment ? "asked, not assigned" : c.work_kind === "design" ? "Sarah"
      : c.work_kind === "research" ? "research-agent" : c.work_kind === "content" ? "docs-agent" : "impl-agent";
  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet">
        <button className="close" onClick={onClose}>✕</button>
        {!p ? (
          <div>
            <div className="d-q" style={{ fontSize: 26, marginBottom: 8, maxWidth: "100%" }}>Describe your sprint.</div>
            <div className="note" style={{ marginBottom: 18, fontSize: 13 }}>Say it in plain words, out loud or typed. The planner turns it into commitments, each carrying the check that will prove it.</div>
            <div className="intent-wrap">
              <textarea className="intent-box" rows={5}
                value={intent + (interim ? (intent.trim() ? " " : "") + interim : "")}
                onChange={(e) => setIntent(e.target.value)} autoFocus />
              {dictation.supported && (
                <button type="button" className={`micbtn ${dictation.listening ? "on" : ""}`} onClick={mic}
                  title={dictation.listening ? "Stop dictation" : "Speak your sprint"}>
                  <span className="micdot" />{dictation.listening ? "Listening…" : "Speak"}
                </button>
              )}
            </div>
            <div className="plan-foot">
              <span className="note">One conversation becomes a working team of people and agents.</span>
              <button className="b primary" onClick={generate} disabled={busy || !intent.trim()}>{busy ? "Planning…" : "Plan the sprint →"}</button>
            </div>
          </div>
        ) : (
        <>
        <div className="intent">{p.intent}</div>
        <div className="src">planned by {p.source === "planner-agent" ? "the Strands planner" : "fixture"} · {p.commitments.length} commitments · {p.rejected.length} refused &nbsp;
          <button className="linky" onClick={() => setP(null)}>edit</button></div>
        <div className="plan-list">{p.commitments.map((c) => (
          <div className="prow" key={c.title}>
            <div><span className="pt">{c.title}</span>{c.judgment && <span className="dtag">Decision</span>}
              <div className={`proof ${c.proof_kind === "review" ? "review" : ""}`}><span className="k">proof:</span> {c.proof}</div>
              {c.judgment && <div className="dnote">this will be asked, not assigned</div>}
              {c.depends_on.length > 0 && <div className="dnote">after: {c.depends_on.join(", ")}</div>}</div>
            <span className="assignee">{assignee(c)}</span>
            <span className="pcost">{c.judgment ? "" : `${c.review_cost}m`}</span>
          </div>
        ))}</div>
        {p.rejected.length > 0 && <>
          <div className="rejected-head">Rejected by the planner</div>
          <div className="rej-intro">Work whose completion could not be proven was not planned.</div>
          <div className="rej-list">{p.rejected.map((r) => (
            <div className="rrow" key={r.title}><div className="rt">{r.title}</div><div className="rr">{r.reason}</div></div>))}</div>
        </>}
        <div className="plan-foot">
          <span className="note">Every commitment carries the check that will prove it. Nothing reaches done on a worker's word.</span>
          <button className="b primary" onClick={approve} disabled={busy}>{busy ? "Approving…" : `Approve ${p.commitments.length} commitments`}</button>
        </div>
        </>
        )}
      </div>
    </div>
  );
}
