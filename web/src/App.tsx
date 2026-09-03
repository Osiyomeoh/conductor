import { useEffect, useState } from "react";
import { useConductor, useTheme } from "./hooks";
import { Glyph } from "./logo";
import { ActivityView, BoardView, CostView, DecisionsView, DecisionOverlay, HomeView, PlanOverlay, RealView, RepoView, TeamView } from "./views";

type ViewName = "home" | "board" | "decisions" | "activity" | "real" | "repo" | "team" | "cost";
const NAV: { view: ViewName; icon: string; label: string }[] = [
  { view: "home", icon: "◎", label: "Home" },
  { view: "board", icon: "▤", label: "Board" },
  { view: "decisions", icon: "◇", label: "Decisions" },
  { view: "activity", icon: "≋", label: "Activity" },
  { view: "real", icon: "⎇", label: "Real execution" },
  { view: "repo", icon: "⌥", label: "Your repo" },
  { view: "team", icon: "◐", label: "Team" },
  { view: "cost", icon: "$", label: "Cost & trust" },
];

export function App() {
  const [view, setView] = useState<ViewName>(() =>
    (location.hash.slice(1) as ViewName) || "home");
  const [openDecision, setOpenDecision] = useState<string | null>(null);
  const [planOpen, setPlanOpen] = useState(false);
  const [dark, toggleTheme] = useTheme();
  const overlayOpen = openDecision !== null || planOpen;
  const { state, tick, answer } = useConductor(overlayOpen);

  useEffect(() => { location.hash = view; }, [view]);

  if (!state) return <div className="app"><aside className="sidebar" /><main className="content" /></div>;

  const n = state.decisions.length;
  const go = (v: ViewName) => setView(v);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="ws"><span className="mark"><span className="glyph"><Glyph /></span></span><span>Conductor</span></div>
        <div className="navlabel">Workspace</div>
        {NAV.map((x) => (
          <button key={x.view} className={`nav ${view === x.view ? "active" : ""}`} onClick={() => go(x.view)}>
            <span className="ic">{x.icon}</span><span>{x.label}</span>
            {x.view === "home" && <span className={`badge ${n === 0 ? "zero" : ""}`}>{n}</span>}
          </button>
        ))}
        <div className="loopchip"><span className="dot" /><span>Loop running</span></div>
        <div className="side-foot">
          <button className="plan" onClick={() => setPlanOpen(true)}><span>+</span><span>Plan a sprint</span></button>
          <div className="run"><button onClick={() => void tick(1)}>Tick</button><button onClick={() => void tick(6)}>Run six</button></div>
          <button className="themebtn" onClick={toggleTheme}><span>{dark ? "◑" : "◐"}</span><span>Theme</span></button>
        </div>
      </aside>

      <main className="content">
        {view === "home" && <HomeView s={state} onOpen={setOpenDecision} onAnswer={(id, c) => void answer(id, c)} onPlan={() => setPlanOpen(true)} />}
        {view === "board" && <BoardView s={state} onTick={(k) => void tick(k)} />}
        {view === "decisions" && <DecisionsView s={state} onOpen={setOpenDecision} onAnswer={(id, c) => void answer(id, c)} />}
        {view === "activity" && <ActivityView />}
        {view === "real" && <RealView />}
        {view === "repo" && <RepoView />}
        {view === "team" && <TeamView />}
        {view === "cost" && <CostView s={state} />}
      </main>

      {openDecision && <DecisionOverlay id={openDecision} onClose={() => setOpenDecision(null)} onAnswer={(id, c) => void answer(id, c)} />}
      {planOpen && <PlanOverlay onClose={() => setPlanOpen(false)} onApproved={() => go("home")} />}
    </div>
  );
}
