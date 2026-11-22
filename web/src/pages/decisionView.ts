/** Wording for the Decision Room. Pure functions, so the rules are tested without a browser. */

/** "due in 3 h", "1 h late", "due tomorrow". Empty when the gate has no due time. */
export function dueText(secondsLeft: number | null | undefined): string {
  if (secondsLeft === null || secondsLeft === undefined) return "";
  const late = secondsLeft < 0;
  const s = Math.abs(secondsLeft);
  if (!late && s < 60) return "due now";
  const min = Math.round(s / 60);
  const hours = Math.round(s / 3600);
  const days = Math.round(s / 86400);
  if (late) return s < 3600 ? `${min} min late` : s < 86400 ? `${hours} h late` : `${days} d late`;
  if (s < 3600) return `due in ${min} min`;
  if (s < 24 * 3600) return `due in ${hours} h`;
  if (s < 48 * 3600) return "due tomorrow";
  return `due in ${days} days`;
}

/** The "who signed" part of an evidence line. Never names anyone the audit does not name. */
export function signatureNote(e: { bootstrapped: boolean; approved_by: string | null; at: string }): string {
  const day = e.at.slice(0, 10);
  if (e.bootstrapped) {
    return e.approved_by ? `bootstrapped · imported by ${e.approved_by} on ${day}` : `bootstrapped · imported on ${day}`;
  }
  return e.approved_by ? `approved by ${e.approved_by}` : "";
}

/** "$0.42", or "$0.0042" for the very small amounts a short step costs. */
export function money(usd: number): string {
  return usd >= 0.01 ? `$${usd.toFixed(2)}` : `$${usd.toFixed(4)}`;
}
