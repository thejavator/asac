import type { State } from "@/lib/status";

/** Money as the portal shows it: two decimals, with a dash for "nothing booked". */
export function usd(v: number): string {
  if (v === 0) return "—";
  if (v < 0.01) return "< $0.01";
  return `$${v.toFixed(2)}`;
}

/** Token counts in compact form (12 400 → "12.4k"). */
export function tokens(n: number): string {
  if (n === 0) return "—";
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}

/** Share of hook runs that passed. `null` means no hook ran: shown as a dash, never as 0 %. */
export function passRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "—";
  return `${Math.round(rate * 100)} %`;
}

/**
 * What a project's row should signal, worst first. A security event outranks a failing run:
 * an agent that tried to rewrite its rules matters more than a red test.
 */
export function health(p: {
  unavailable: boolean;
  integrity_violations: number;
  sandbox_denials: number;
  problems: number;
  pending_gates: number;
}): [State, string] {
  if (p.unavailable) return ["bad", "Unavailable"];
  if (p.integrity_violations > 0) return ["bad", "Rules tampered"];
  if (p.problems > 0) return ["bad", "Runs need attention"];
  if (p.sandbox_denials > 0) return ["wait", "Sandbox refusals"];
  if (p.pending_gates > 0) return ["wait", "Decisions waiting"];
  return ["ok", "On track"];
}
