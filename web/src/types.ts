// Typed contract for the Conductor API. These mirror conductor/server.py's
// state()/team()/decision_detail() shapes — the payoff of TypeScript is that a
// drift between backend and frontend becomes a compile error, not a runtime one.

export type StatusName =
  | "pending" | "dispatched" | "claimed_done" | "verifying" | "done"
  | "rejected" | "blocked" | "at_risk" | "held" | "escalated";

export interface BoardItem {
  id: string;
  title: string;
  status: StatusName;
  owner: string | null;
  reviewer: string | null;
  risk: number;
  attempts: number;
  speculative: boolean;
  branch: string | null;
  work_kind: string;
  review_cost: number;
  evidence: { kind: string; spec: string; passed: boolean | null; detail: string };
  reason: string;
}

export interface DecisionSummary {
  id: string;
  question: string;
  options: string[];
  unblocks: number;
  commitments: number;
  review_minutes: number;
  compressed_from: number;
  branches: number;
  prebuilt: number;
  spent: number;
  needs_framing: boolean;
}

export interface Attention {
  reviewer: string; spent: number; committed: number; remaining: number; total: number;
}

export interface Trust {
  worker: string; type: "human" | "agent"; probation: boolean;
  principal: string | null; detail: string;
}

export interface Cost {
  total: number; verified: number; rejected: number; discarded: number;
  per_verified: number; by_model: Record<string, number>;
}

export interface Metrics {
  dispatched: number; claims: number; claims_rejected: number; verified: number;
  escalations_raised: number; questions_asked: number; interruptions: number;
  speculative_cost: number; held: number;
}

export interface State {
  board: BoardItem[];
  decisions: DecisionSummary[];
  attention: Attention[];
  trust: Trust[];
  cost: Cost;
  metrics: Metrics;
  events: string[];
  compression: string;
  in_flight: number;
}

export interface BranchDetail {
  option: string; cost: number; verified: number; total: number;
  chosen: boolean; discarded: boolean;
  work: { title: string; status: StatusName; evidence: string; passed: boolean | null }[];
}

export interface DecisionDetail {
  id: string; question: string; options: string[]; answer: string | null;
  unblocks: number; spent: number; needs_framing: boolean;
  branches: BranchDetail[];
  compressed_from: { id: string; title: string }[];
  error?: string;
}

export interface Member {
  id: string; name: string; type: "human" | "agent"; purpose: string;
  skills: { kind: string; score: number | null; passes: number; total: number }[];
  probation: boolean; principal: string | null; scopes: string[]; budget: number | null;
}

export interface Proposal { kind: string; queued: number; question: string; options: string[]; }
export interface Team { members: Member[]; proposals: Proposal[]; }

export interface PlanItem {
  title: string; proof: string; proof_kind: string; work_kind: string;
  review_cost: number; judgment: boolean; consequential: boolean;
  depends_on: string[]; options: string[];
}
export interface Plan {
  intent: string; goal: string; source: string;
  commitments: PlanItem[]; rejected: { title: string; reason: string }[];
  assumptions: string[];
}

export interface RepoSnapshot {
  base: string;
  log: string[];
  files: Record<string, string>;
  path: string | null;
}
export interface RealState extends State {
  repo: RepoSnapshot;
  live?: boolean;
}

export interface RepoConnect extends Partial<RealState> {
  enabled: boolean;
  connected: boolean;
  path?: string | null;
  live?: boolean;
}

export interface ActivityEvent {
  seq: number; at: string; kind: string; tone: string; verb: string;
  actor: string | null; title: string | null; detail: string;
}
export interface Activity {
  events: ActivityEvent[];
  by_worker: Record<string, { verified: number; caught: number }>;
}
