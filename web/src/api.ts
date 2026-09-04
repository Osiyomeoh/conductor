import type { State, Team, DecisionDetail, Plan, Activity, RealState, RepoConnect, GitHubState } from "./types";

// Thin typed client. Every call returns a typed promise, so a view that reads
// a field the API does not send fails to compile.
async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: { "accept": "application/json" } });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  state: () => get<State>("/api/state"),
  team: () => get<Team>("/api/team"),
  activity: () => get<Activity>("/api/activity"),
  plan: (intent?: string) => post<Plan>("/api/plan", { intent: intent ?? "" }),
  approve: (intent: string) => post<State & { approved: number; planned_by: string }>("/api/approve", { intent }),
  decision: (id: string) => get<DecisionDetail>(`/api/decision?id=${encodeURIComponent(id)}`),
  tick: (ticks: number) => post<State>("/api/tick", { ticks }),
  answer: (decision_id: string, choice: string) =>
    post<State>("/api/answer", { decision_id, choice }),
  realState: () => get<RealState>("/api/real/state"),
  realRun: (ticks: number, live: boolean) => post<RealState>("/api/real/run", { ticks, live }),
  realReset: (live: boolean) => post<RealState>("/api/real/reset", { live }),
  repoStatus: () => get<RepoConnect>("/api/repo"),
  repoConnect: (path: string) => post<RepoConnect>("/api/repo/connect", { path }),
  repoTask: (t: { title: string; file: string; check: string }) => post<RepoConnect>("/api/repo/task", t),
  repoRun: (ticks: number) => post<RepoConnect>("/api/repo/run", { ticks }),
  repoDisconnect: () => post<RepoConnect>("/api/repo/disconnect", {}),
  githubStatus: () => get<GitHubState>("/api/github"),
  githubConnect: () => post<GitHubState>("/api/github/connect", {}),
  githubTask: (t: { title: string; file: string; check: string }) => post<GitHubState>("/api/github/task", t),
  githubRun: (ticks: number) => post<GitHubState>("/api/github/run", { ticks }),
};
