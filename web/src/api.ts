import type { State, Team, DecisionDetail, Plan, Activity, RealState, RepoConnect, GitHubState } from "./types";

const TOKEN_KEY = "conductor_token";

// After the identity provider redirects back with #id_token=..., capture it,
// persist it, and clean it out of the URL. Otherwise read a stored token.
function authToken(): string | null {
  try {
    const frag = new URLSearchParams(location.hash.replace(/^#/, ""));
    const t = frag.get("id_token") || frag.get("access_token");
    if (t) {
      localStorage.setItem(TOKEN_KEY, t);
      history.replaceState(null, "", location.pathname + location.search);
      return t;
    }
    return localStorage.getItem(TOKEN_KEY);
  } catch { return null; }
}

export function signOut(): void {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

function authHeaders(base: Record<string, string>): Record<string, string> {
  const t = authToken();
  return t ? { ...base, authorization: `Bearer ${t}` } : base;
}

// Thin typed client. Every call returns a typed promise, so a view that reads
// a field the API does not send fails to compile.
async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: authHeaders({ accept: "application/json" }) });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: authHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}
async function del<T>(path: string): Promise<T> {
  const r = await fetch(path, { method: "DELETE", headers: authHeaders({ accept: "application/json" }) });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

export interface WhoAmI { subject: string; tenant: string; email: string | null; roles: string[]; }
export interface AuthConfig { mode: "disabled" | "session" | "sso"; login_url: string | null; }
export interface OrgMember { subject: string; role: string; email: string | null; added_by: string | null; }

// Capture a token from the redirect fragment immediately on load, before the
// router rewrites the hash.
authToken();

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
  whoami: () => get<WhoAmI>("/api/whoami"),
  authConfig: () => get<AuthConfig>("/api/auth/config"),
  hire: (kind: string) => post<Team>("/api/team/hire", { kind }),
  members: () => get<{ members: OrgMember[] }>("/api/members"),
  addMember: (m: { subject: string; role: string; email?: string }) => post<{ members: OrgMember[] }>("/api/members", m),
  removeMember: (subject: string) => del<{ members: OrgMember[] }>(`/api/members/${encodeURIComponent(subject)}`),
};
