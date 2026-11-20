import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Chip } from "../components/Chip";
import { FlowGraph } from "../components/FlowGraph";
import { Link } from "../components/Link";
import { TriggerLink } from "../components/TriggerLink";

export function DecisionRoom({ pid, me, go }: { pid?: string; me: string; go: (to: string) => void }) {
  const [onlyMine, setOnlyMine] = useState(false);
  const qc = useQueryClient();
  const gates = useQuery({
    queryKey: ["decisions", pid ?? "all", onlyMine],
    queryFn: () => unwrap(api.GET("/decisions", { params: { query: { project: pid, mine: onlyMine } } })),
  });
  const [picked, setPicked] = useState<string>();
  const [comment, setComment] = useState("");
  const list = gates.data ?? [];
  const gate = list.find((g) => g.gate_id === picked) ?? list[0];
  const gpid = gate?.project_id ?? "";
  const run = useQuery({
    enabled: !!gate,
    queryKey: ["run", gpid, gate?.run_id],
    queryFn: () => unwrap(api.GET("/projects/{pid}/runs/{run_id}", { params: { path: { pid: gpid, run_id: gate!.run_id } } })),
  });
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      unwrap(api.POST("/projects/{pid}/gates/{gate_id}/decision", {
        params: { path: { pid: gpid, gate_id: gate!.gate_id } },
        body: { decision, comment },
        headers: csrfHeader(),
      })),
    onSuccess: () => {
      setComment("");
      void qc.invalidateQueries();
    },
  });

  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid ?? "All projects"} / Decision Room</p>
      <div className="page-head">
        <div>
          <h1>Decision Room</h1>
          <p>Decisions that wait for a person{pid ? " in this project" : ", in every project you can see"}. Each one shows what was built, what was checked and who signed before you.</p>
        </div>
        <label className="check"><input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} /> Only what I can sign</label>
      </div>
      {gates.isError && <p role="alert">Could not load decisions: {gates.error.message}</p>}
      {gates.data && list.length === 0 && <p className="soft">Nothing is waiting for a decision.</p>}
      {gate && (
        <div className="workspace">
          <section className="queue" aria-labelledby="queue-h">
            <header><h2 id="queue-h">Waiting</h2><span className="faint">{list.length} decisions</span></header>
            <ol>
              {list.map((g) => (
                <li key={g.gate_id}>
                  <a className="item" href={`#${g.gate_id}`} data-urgency="none" aria-current={g.gate_id === gate.gate_id ? "true" : undefined}
                     onClick={(e) => { e.preventDefault(); setPicked(g.gate_id); }}>
                    <span className="title">{g.step_id}</span>
                    <span className="meta">{!pid && <span>{g.project_name}</span>}<span className="mono">{g.run_id}</span><span>{g.role ?? "any role"}</span></span>
                  </a>
                </li>
              ))}
            </ol>
          </section>
          <article className="sheet" aria-labelledby="decision-h">
            <header>
              <Chip state="wait">Waiting for {gate.role ?? "any role"}</Chip>
              <h2 id="decision-h">Approve {gate.step_id}</h2>
              <dl className="facts">
                {!pid && <div><dt>Project</dt><dd>{gate.project_name}</dd></div>}
                <div><dt>Run</dt><dd className="mono"><Link to={`/p/${gate.project_id}/runs/${gate.run_id}`} go={go}>{gate.run_id}</Link></dd></div>
                {run.data?.trigger && <div><dt>Trigger</dt><dd><TriggerLink trigger={run.data.trigger} /></dd></div>}
                <div><dt>Requested</dt><dd className="mono">{gate.requested_at}</dd></div>
                {gate.timeout_at && <div><dt>Due</dt><dd className="mono">{gate.timeout_at}</dd></div>}
              </dl>
            </header>
            {run.data && (
              <>
                <div className="section"><h3>Where this run stands</h3><FlowGraph steps={run.data.run.steps} /></div>
                <div className="section">
                  <h3>Evidence chain</h3>
                  <ol className="ledger">
                    {run.data.evidence.map((e) => (
                      <li key={e.evidence_id} className="entry" data-kind={e.bootstrapped ? "boot" : "agent"}>
                        <div className="line"><b>{e.evidence_id}</b><span className="kind">{e.bootstrapped ? "bootstrapped" : `produced by ${e.produced_by}`}</span></div>
                      </li>
                    ))}
                    <li className="entry" data-kind="pending">
                      <div className="line"><b>{gate.step_id}</b><span className="kind">waiting for {gate.role ?? "any role"}</span></div>
                      <div className="produced">Your signature produces this evidence.</div>
                    </li>
                  </ol>
                </div>
              </>
            )}
            <div className="section decide">
              <h3>Your decision</h3>
              {gate.can_decide ? (
                <form onSubmit={(e) => { e.preventDefault(); decide.mutate("approve"); }}>
                  <label htmlFor="comment">Comment</label>
                  <textarea id="comment" name="comment" maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
                  <p className="hint">Required if you reject. Kept in the audit trail with your name.</p>
                  {decide.isError && <p role="alert" className="notice"><span aria-hidden="true">⚠</span><span>{decide.error.message}</span></p>}
                  <div className="actions">
                    <button className="btn btn-primary" type="submit" disabled={decide.isPending}>Approve</button>
                    <button className="btn btn-danger" type="button" disabled={decide.isPending || !comment.trim()} onClick={() => decide.mutate("reject")}>Reject</button>
                    <span className="alone">Signed as {me}</span>
                  </div>
                </form>
              ) : (
                <p className="notice"><span aria-hidden="true">⚠</span><span>This decision needs the role {gate.role}. You can read it but not sign it.</span></p>
              )}
            </div>
          </article>
        </div>
      )}
    </>
  );
}
