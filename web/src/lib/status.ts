export type State = "wait" | "ok" | "bad" | "stop" | "idle";

const RUN: Record<string, [State, string]> = {
  running: ["wait", "Running"],
  gate_waiting: ["wait", "Waiting for a decision"],
  completed: ["ok", "Completed"],
  failed: ["bad", "Failed"],
  blocked: ["bad", "Blocked"],
  killed: ["stop", "Stopped"],
};
const STEP: Record<string, [State, string]> = {
  completed: ["ok", "Done"],
  running: ["wait", "Running"],
  gate_waiting: ["wait", "Your decision"],
  failed: ["bad", "Failed"],
  blocked: ["bad", "Blocked"],
  pending: ["idle", "Not started"],
  killed: ["stop", "Stopped"],
};

export const runState = (s: string): [State, string] => RUN[s] ?? ["idle", s];
export const stepState = (s: string): [State, string] => STEP[s] ?? ["idle", s];
