import { useQueries, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { RunChip } from "../components/Chip";
import { Link } from "../components/Link";

const PROBLEMS = ["failed", "blocked", "killed"];

export function ErrorsPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const qs = useQueries({
    queries: PROBLEMS.map((status) => ({
      queryKey: ["runs", pid, status, ""],
      queryFn: () => unwrap(api.GET("/projects/{pid}/runs", { params: { path: { pid }, query: { status, limit: 100 } } })),
    })),
  });
  const failed = qs.find((q) => q.isError);
  const items = qs.flatMap((q) => q.data?.items ?? []).sort((a, b) => b.created_at.localeCompare(a.created_at));
  const ev = useQuery({
    queryKey: ["audit-problems", pid],
    queryFn: () => unwrap(api.GET("/projects/{pid}/audit", { params: { path: { pid }, query: { problems: true, limit: 50 } } })),
  });
  const events = ev.data?.items ?? [];
  const loading = qs.some((q) => q.isLoading);
  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid} / Errors</p>
      <div className="page-head"><div><h1>Errors</h1><p>Runs that failed, were blocked by a policy or hook, or were stopped. Open one to see where it stopped.</p></div></div>
      {failed?.error && <p role="alert">Could not load errors: {failed.error.message}</p>}
      {!loading && !failed && items.length === 0 && <p className="soft">No run needs attention.</p>}
      {items.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Run</th><th>Pipeline</th><th>Status</th><th>Stopped at</th><th className="hide-sm">Created</th></tr></thead>
            <tbody>
              {items.map((r) => {
                const at = r.steps.find((s) => s.status === "failed" || s.status === "blocked" || s.status === "killed");
                return (
                  <tr key={r.run_id} data-state="bad">
                    <td className="mono"><Link to={`/p/${pid}/runs/${r.run_id}`} go={go}>{r.run_id}</Link></td>
                    <td>{r.pipeline}</td><td><RunChip status={r.status} /></td>
                    <td className="mono">{at?.id ?? "n/a"}</td><td className="mono hide-sm">{r.created_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <h2>Events</h2>
      <p className="soft">Denied approvals, failed or blocked steps, hook failures, expired gates, escalations and stopped runs, newest first.</p>
      {ev.isError && <p role="alert">Could not load events: {ev.error.message}</p>}
      {ev.data && events.length === 0 && <p className="soft">No event needs attention.</p>}
      {events.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th className="hide-sm">When</th><th>Event</th><th>Run</th><th>Step</th><th>Detail</th></tr></thead>
            <tbody>
              {events.map((a) => (
                <tr key={a.seq} data-state="bad">
                  <td className="mono hide-sm">{a.at}</td><td className="mono">{a.action}</td>
                  <td className="mono">{a.run_id ? <Link to={`/p/${pid}/runs/${a.run_id}`} go={go}>{a.run_id}</Link> : ""}</td>
                  <td className="mono">{a.step_id ?? ""}</td><td>{a.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
