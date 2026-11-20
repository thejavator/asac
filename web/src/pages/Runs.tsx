import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { RunChip } from "../components/Chip";
import { Link } from "../components/Link";

const STATUSES = ["", "running", "gate_waiting", "completed", "failed", "blocked", "killed"];

function StartRun({ pid, go }: { pid: string; go: (to: string) => void }) {
  const pipes = useQuery({ queryKey: ["pipelines", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/pipelines", { params: { path: { pid } } })) });
  const [name, setName] = useState("");
  const [open, setOpen] = useState(false);
  const pipeline = name || pipes.data?.[0]?.name || "";
  const plan = useQuery({
    enabled: open && !!pipeline,
    queryKey: ["plan", pid, pipeline],
    queryFn: () => unwrap(api.GET("/projects/{pid}/pipelines/{name}/plan", { params: { path: { pid, name: pipeline } } })),
  });
  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{pid}/runs", { params: { path: { pid } }, body: { pipeline }, headers: csrfHeader() })),
    onSuccess: (r) => go(`/p/${pid}/runs/${r.run_id}`),
  });
  if (!open) return <p><button className="btn btn-primary" type="button" onClick={() => setOpen(true)}>Start a run</button></p>;
  return (
    <section className="sheet" aria-label="Start a run">
      <h2>Start a run</h2>
      <label className="soft" htmlFor="pipe">Pipeline</label>{" "}
      <select className="field" id="pipe" value={pipeline} onChange={(e) => setName(e.target.value)}>
        {(pipes.data ?? []).map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
      </select>
      {plan.data && (
        <>
          <p>
            {plan.data.steps.length} steps, estimated {plan.data.estimated_tokens.toLocaleString("en")} tokens
            {plan.data.budget_tokens != null && <> of a {plan.data.budget_tokens.toLocaleString("en")} budget</>}.
            {plan.data.over_budget && <b role="alert"> Over budget: raise the run budget before starting.</b>}
          </p>
          <ol className="timeline" aria-label="Plan">
            {plan.data.steps.map((s) => (
              <li key={s.id}><span className="sub"><b>{s.id}</b> {s.agent} · {s.mode}{s.gate ? ` · gate ${s.gate}` : ""}</span></li>
            ))}
          </ol>
        </>
      )}
      {plan.isError && <p role="alert">Could not plan: {plan.error.message}</p>}
      {start.isError && <p role="alert">Could not start the run: {start.error.message}</p>}
      <p>
        <button className="btn btn-primary" type="button" disabled={!plan.data || plan.data.over_budget || start.isPending} onClick={() => start.mutate()}>Start run</button>{" "}
        <button className="btn" type="button" onClick={() => setOpen(false)}>Cancel</button>
      </p>
    </section>
  );
}

export function RunsPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const [status, setStatus] = useState("");
  const [needle, setNeedle] = useState("");
  const q = useInfiniteQuery({
    queryKey: ["runs", pid, status, needle],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/projects/{pid}/runs", { params: { path: { pid }, query: { status, q: needle, cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid} / Runs</p>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p>Every run of this project, newest first.</p>
        </div>
        <form className="quiet-form" aria-label="Filter runs" onSubmit={(e) => e.preventDefault()}>
          <label className="soft" htmlFor="status">Status</label>
          <select className="field" id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All"}</option>)}
          </select>
          <label className="soft" htmlFor="needle">Search</label>
          <input className="field" id="needle" value={needle} onChange={(e) => setNeedle(e.target.value)} />
        </form>
      </div>
      <StartRun pid={pid} go={go} />
      {q.isError && <p role="alert">Could not load runs: {q.error.message}</p>}
      {q.data && items.length === 0 && <p className="soft">No run matches. Start one above, with <span className="mono">asac apply</span>, or from a trigger.</p>}
      {items.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Run</th><th>Pipeline</th><th>Status</th><th className="hide-sm">Steps</th><th className="hide-sm">Created</th></tr></thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.run_id}>
                  <td className="mono"><Link to={`/p/${pid}/runs/${r.run_id}`} go={go}>{r.run_id}</Link></td>
                  <td>{r.pipeline}</td>
                  <td><RunChip status={r.status} /></td>
                  <td className="hide-sm">{r.steps.filter((s) => s.status === "completed").length} of {r.steps.length}</td>
                  <td className="mono hide-sm">{r.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {q.hasNextPage && (
        <p><button className="btn" type="button" disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Load more</button></p>
      )}
    </>
  );
}
