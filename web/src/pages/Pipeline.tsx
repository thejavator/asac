import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Link } from "../components/Link";

export function PipelinePage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const q = useQuery({ queryKey: ["pipelines", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/pipelines", { params: { path: { pid } } })) });
  const [name, setName] = useState<string>();
  const [stepId, setStepId] = useState<string>();
  const pipe = q.data?.find((p) => p.name === name) ?? q.data?.[0];
  const step = pipe?.steps.find((s) => s.id === stepId) ?? pipe?.steps[0];
  const w = 150, gap = 80;
  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid} / Pipeline</p>
      <div className="page-head">
        <div><h1>Pipeline {pipe && <span className="mono">{pipe.name}</span>}</h1>
          <p>Steps, the evidence each one needs and produces, and who signs each gate.</p></div>
        <Link to={`/p/${pid}/pipeline/edit`} go={go}>Edit pipeline</Link>
        {q.data && q.data.length > 1 && (
          <form className="quiet-form" aria-label="Choose pipeline" onSubmit={(e) => e.preventDefault()}>
            <label className="soft" htmlFor="pipe">Pipeline</label>
            <select className="field" id="pipe" value={pipe?.name} onChange={(e) => { setName(e.target.value); setStepId(undefined); }}>
              {q.data.map((p) => <option key={p.name}>{p.name}</option>)}
            </select>
          </form>
        )}
      </div>
      {q.isError && <p role="alert">Could not load pipelines: {q.error.message}</p>}
      {pipe && step && (
        <article className="sheet" aria-label={`${pipe.name} pipeline`}>
          <div className="section">
            <h3>Flow and evidence</h3>
            <div className="scroll-x">
              <svg className="pipe-graph" viewBox={`0 0 ${pipe.steps.length * (w + gap) - gap + 16} 100`} role="img"
                   aria-label={`Steps in order: ${pipe.steps.map((s) => s.id).join(", ")}`}>
                {pipe.steps.slice(1).map((s, i) => <path key={s.id} className="edge" d={`M${8 + i * (w + gap) + w} 42 H${8 + (i + 1) * (w + gap)}`} />)}
                {pipe.steps.map((s, i) => {
                  const x = 8 + i * (w + gap);
                  return (
                    <g key={s.id} className="node" data-state="idle" aria-current={s.id === step.id ? "step" : undefined}
                       tabIndex={0} role="button" onClick={() => setStepId(s.id)}
                       onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setStepId(s.id); }}>
                      <rect x={x} y={10} width={w} height={66} rx={6} />
                      <text x={x + 12} y={32}>{s.id}</text>
                      <text className="sub" x={x + 12} y={50}>{s.agent ?? "no agent"}</text>
                      <text className="sub" x={x + 12} y={66}>{s.gate_role ? `gate: ${s.gate_role}` : "no gate"}</text>
                    </g>
                  );
                })}
              </svg>
            </div>
            <p className="source-note">Each arrow carries the evidence that must exist before the next step may start.</p>
          </div>
          <div className="section">
            <h3>Step inspector</h3>
            <h4 className="inspector-title">{step.id}</h4>
            <dl className="fields">
              <dt>Agent</dt><dd className="mono">{step.agent ?? "none"}</dd>
              <dt>Depends on</dt><dd className="mono">{step.depends_on.join(", ") || "nothing"}</dd>
              <dt>Requires</dt><dd className="mono">{step.requires.join(", ") || "nothing"}</dd>
              <dt>Produces</dt><dd className="mono">{step.produces.join(", ") || "nothing"}</dd>
              <dt>Gate</dt><dd>{step.gate_role ? `signed by ${step.gate_role}` : "no human gate"}</dd>
            </dl>
            <p className="source-note">Read only. Changes are proposed from the editor and saved to git through a merge request.</p>
          </div>
        </article>
      )}
    </>
  );
}
