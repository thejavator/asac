import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Chip, RunChip, stepState } from "../components/Chip";
import { FlowGraph } from "../components/FlowGraph";
import { Link } from "../components/Link";
import { TriggerLink } from "../components/TriggerLink";

const TABS = ["steps", "output", "deliverables", "hooks", "evidence", "audit"] as const;
type Tab = (typeof TABS)[number];

export function RunDetailPage({ pid, runId, go }: { pid: string; runId: string; go: (to: string) => void }) {
  const q = useQuery({
    queryKey: ["run", pid, runId],
    queryFn: () => unwrap(api.GET("/projects/{pid}/runs/{run_id}", { params: { path: { pid, run_id: runId } } })),
    // a run that is working refreshes by itself; a finished or waiting one does not
    refetchInterval: (query) => (query.state.data?.run.status === "running" ? 2000 : false),
  });
  const qc = useQueryClient();
  const stop = useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{pid}/runs/{run_id}/stop", { params: { path: { pid, run_id: runId } }, headers: csrfHeader() })),
    onSuccess: () => qc.invalidateQueries(),
  });
  const [tab, setTab] = useState<Tab>("steps");
  const [picked, setPicked] = useState<string>();
  if (q.isError) return <p role="alert">Could not load this run: {q.error.message}</p>;
  if (!q.data) return <p className="faint">Loading…</p>;
  const { run, evidence, gates, audit } = q.data;
  const outputs = audit.filter((a) => a.action === "runner.output");
  const hooks = audit.filter((a) => a.action === "hook.passed" || a.action === "hook.failed");
  const done = run.steps.filter((s) => s.status === "completed").length;
  const current = picked ?? run.steps.find((s) => s.status !== "completed" && s.status !== "pending")?.id ?? run.steps[0]?.id;
  const label: Record<Tab, string> = { steps: "Steps", output: "Output", deliverables: "Deliverables", hooks: "Hooks", evidence: "Evidence", audit: "Audit" };
  const count: Record<Tab, number | undefined> = { steps: undefined, output: outputs.length || undefined, deliverables: q.data.artifacts.length || undefined, hooks: hooks.length || undefined, evidence: evidence.length, audit: audit.length };
  return (
    <>
      <p className="crumbs">
        <Link to="/" go={go}>All projects</Link> / <Link to={`/p/${pid}/runs`} go={go}>{pid}</Link> / <span className="mono">{run.run_id}</span>
      </p>
      <article className="sheet" aria-labelledby="run-h">
        <header className="run-head">
          <RunChip status={run.status} />
          <h1 id="run-h">{run.pipeline} <span className="mono">{run.run_id}</span></h1>
          {(run.status === "running" || run.status === "gate_waiting") && (
            <p>
              {run.status === "running" && <span className="soft" role="status">Live: refreshing every 2 seconds. </span>}
              <button className="btn" type="button" disabled={stop.isPending}
                onClick={() => { if (window.confirm("Stop this run? It cannot be resumed.")) stop.mutate(); }}>Stop run</button>
              {stop.isError && <span role="alert"> Could not stop the run: {stop.error.message}</span>}
            </p>
          )}
          <dl className="facts">
            <div><dt>Run</dt><dd className="mono">{run.run_id}</dd></div>
            <div><dt>Pipeline</dt><dd>{run.pipeline}</dd></div>
            {q.data.trigger && <div><dt>Trigger</dt><dd><TriggerLink trigger={q.data.trigger} /></dd></div>}
            <div><dt>Created</dt><dd className="mono">{run.created_at}</dd></div>
          </dl>
          <dl className="metrics">
            <div><dt>Steps</dt><dd>{done} <small>of {run.steps.length} done</small></dd></div>
            <div><dt>Decisions</dt><dd>{gates.filter((g) => g.status === "approved").length} <small>approved</small></dd></div>
            <div><dt>Evidence</dt><dd>{evidence.length}</dd></div>
            <div><dt>Spend</dt><dd>{q.data.spend.tokens.toLocaleString("en")} <small>tokens · ${q.data.spend.cost_usd.toFixed(2)}</small></dd></div>
          </dl>
        </header>
        <ul className="tabs" aria-label="Run sections">
          {TABS.map((t) => (
            <li key={t}>
              <a href={`#${t}`} aria-current={tab === t ? "page" : undefined} onClick={(e) => { e.preventDefault(); setTab(t); }}>
                {label[t]} {count[t] !== undefined && <span className="n">{count[t]}</span>}
              </a>
            </li>
          ))}
        </ul>

        {tab === "steps" && (
          <>
            <div className="section"><h3>Pipeline</h3><FlowGraph steps={run.steps} /></div>
            <div className="steps-layout">
              <ol className="timeline" aria-label="Steps">
                {run.steps.map((s) => {
                  const [state, text] = stepState(s.status);
                  const sym = { ok: "✓", wait: "◔", bad: "✕", stop: "■", idle: "○" }[state];
                  return (
                    <li key={s.id}>
                      <a href={`#${s.id}`} data-state={state} aria-current={s.id === current ? "step" : undefined}
                         onClick={(e) => { e.preventDefault(); setPicked(s.id); }}>
                        <span className="sym" aria-hidden="true">{sym}</span><b>{s.id}</b><span className="sub">{text}</span>
                      </a>
                    </li>
                  );
                })}
              </ol>
              <div className="detail">
                <h2>{current}</h2>
                {gates.filter((g) => g.step_id === current).map((g) => (
                  <p key={g.gate_id} className="by">
                    Gate <span className="mono">{g.gate_id}</span> · {g.role ?? "any role"} ·{" "}
                    <Chip state={g.status === "pending" ? "wait" : g.status === "approved" ? "ok" : "bad"}>{g.status}</Chip>
                    {g.comment && <> · “{g.comment}”</>}
                    {g.status === "pending" && g.can_decide && <> · <Link to={`/p/${pid}/decisions`} go={go}>Decide in Decision Room</Link></>}
                  </p>
                ))}
              </div>
            </div>
          </>
        )}

        {tab === "output" && (
          <div className="section">
            <h3>Runner output</h3>
            {outputs.length === 0 ? <p className="soft">No step has run in a runner yet.</p> : outputs.map((o) => {
              const [head, ...rest] = o.detail.split("\n");
              return (
                <div key={o.seq}>
                  <p className="soft"><b>{o.step_id}</b> <span className="mono">{head}</span></p>
                  <pre className="source output" tabIndex={0}>{rest.join("\n")}</pre>
                </div>
              );
            })}
          </div>
        )}

        {tab === "deliverables" && (
          <div className="section">
            <h3>Deliverables</h3>
            {q.data.artifacts.length === 0 ? <p className="soft">No files were stored for this run.</p> : (
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>File</th><th>Step</th><th>Size</th><th className="hide-sm">SHA-256</th></tr></thead>
                  <tbody>
                    {q.data.artifacts.map((a) => (
                      <tr key={a.name}>
                        <td><a href={`/api/v1/projects/${encodeURIComponent(pid)}/runs/${encodeURIComponent(run.run_id)}/artifacts/${encodeURIComponent(a.name)}`} download>{a.name}</a></td>
                        <td>{a.step_id}</td>
                        <td className="mono">{a.size.toLocaleString("en")} B</td>
                        <td className="mono hide-sm">{a.sha256.slice(0, 16)}…</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === "hooks" && (
          <div className="section">
            <h3>Hook results</h3>
            {hooks.length === 0 ? <p className="soft">No hook has run for this run.</p> : hooks.map((h) => {
              const [head, ...rest] = h.detail.split("\n");
              const { name, moment } = hookMoment(head);
              return (
                <div key={h.seq}>
                  <p className="soft">
                    <Chip state={h.action === "hook.passed" ? "ok" : "bad"}>{h.action === "hook.passed" ? "Passed" : "Failed"}</Chip>{" "}
                    <span className="mono">{name}</span> {moment} <b>{h.step_id}</b>
                  </p>
                  {rest.length > 0 && <pre className="source output" tabIndex={0}>{rest.join("\n")}</pre>}
                </div>
              );
            })}
          </div>
        )}

        {tab === "evidence" && (
          <div className="section">
            <h3>Evidence chain</h3>
            {evidence.length === 0 ? <p className="soft">No evidence yet.</p> : (
              <ol className="ledger">
                {evidence.map((e) => (
                  <li key={e.evidence_id} className="entry" data-kind={e.bootstrapped ? "boot" : e.approved_by ? "human" : "agent"}>
                    <div className="line"><b>{e.evidence_id}</b>
                      <span className="kind">{e.bootstrapped ? "bootstrapped" : `produced by ${e.produced_by}`}{e.approved_by && ` · approved by ${e.approved_by}`}</span>
                    </div>
                    <div className="produced">{e.at}</div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}

        {tab === "audit" && (
          <div className="section">
            <h3>Audit trail</h3>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th className="hide-sm">When</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.seq}><td className="mono hide-sm">{a.at}</td><td>{a.actor}</td><td className="mono">{a.action}</td><td>{a.detail}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </article>
    </>
  );
}

/** "pre_tool no-secrets" -> before the agent of the step; "post_step x" -> after the step.
 *  Audits written before the moment was recorded have only the name: say "during". */
export function hookMoment(head: string): { name: string; moment: string } {
  const [first, ...more] = head.split(" ");
  if (more.length > 0 && first === "pre_tool") return { name: more.join(" "), moment: "before the agent of step" };
  if (more.length > 0 && first === "post_step") return { name: more.join(" "), moment: "after step" };
  return { name: head, moment: "during step" };
}
