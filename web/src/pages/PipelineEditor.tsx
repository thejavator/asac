import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, csrfHeader, unwrap, type Schema } from "../api/client";
import { Chip } from "../components/Chip";
import { Link } from "../components/Link";
import { PipelineGraph } from "../components/PipelineGraph";
import { YamlEditor } from "../components/YamlEditor";

type Finding = Schema["FindingOut"];

const lineOf = (f: Finding, text: string): number | undefined => {
  // findings carry a YAML path such as pipelines.feature.steps.review; point at its last key
  const last = f.path.split(".").filter(Boolean).pop();
  if (!last) return undefined;
  const i = text.split("\n").findIndex((l) => l.includes(`${last}:`));
  return i >= 0 ? i + 1 : undefined;
};

const STATUS: Record<string, [string, string]> = {
  draft: ["idle", "Draft"], proposed: ["wait", "Waiting for review"], applied: ["ok", "Merged"], closed: ["stop", "Closed"],
};

function DraftsList({ pid, go, current }: { pid: string; go: (to: string) => void; current?: string }) {
  const q = useQuery({ queryKey: ["pipe-drafts", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/pipeline/drafts", { params: { path: { pid } } })) });
  if (q.isError) return <p role="alert">Could not load drafts: {q.error.message}</p>;
  if (!q.data) return null;
  return (
    <div className="section">
      <h3>Drafts</h3>
      {q.data.length === 0 ? <p className="source-note">No drafts yet. Save your first edit to create one.</p> : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Draft</th><th>Author</th><th>Updated</th><th>Status</th><th>Change request</th></tr></thead>
            <tbody>
              {q.data.map((d) => {
                const [state, label] = STATUS[d.status] ?? ["idle", d.status];
                return (
                  <tr key={d.id} aria-current={d.id === current ? "true" : undefined}>
                    <td><Link to={`/p/${pid}/pipeline/edit/${d.id}`} go={go}>{d.id}</Link></td>
                    <td>{d.author}</td><td className="mono">{d.updated_at}</td>
                    <td><Chip state={state as never}>{label}</Chip></td>
                    <td>{d.change_request_url ? <a href={d.change_request_url} rel="noreferrer noopener" target="_blank">Open</a> : <span className="soft">none</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Diff({ text }: { text: string }) {
  if (!text) return <p className="source-note">No changes yet.</p>;
  return (
    <pre className="diff" aria-label="Changes against the base file">
      {text.split("\n").map((l, i) => (
        <span key={i} className={l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : undefined}>{l}{"\n"}</span>
      ))}
    </pre>
  );
}

export function PipelineEditorPage({ pid, draftId, go }: { pid: string; draftId?: string; go: (to: string) => void }) {
  const qc = useQueryClient();
  const base = `/projects/{pid}/pipeline` as const;
  const source = useQuery({ queryKey: ["pipe-source", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/pipeline/source", { params: { path: { pid } } })), enabled: !draftId, retry: false });
  const draft = useQuery({
    queryKey: ["pipe-draft", pid, draftId],
    queryFn: () => unwrap(api.GET("/projects/{pid}/pipeline/drafts/{draft_id}", { params: { path: { pid, draft_id: draftId! } } })),
    enabled: !!draftId, retry: false,
  });
  const [text, setText] = useState<string>();
  const [stepId, setStepId] = useState<string>();
  const [pipeName, setPipeName] = useState<string>();
  const [conflict, setConflict] = useState<{ diff: string } | null>(null);
  const original = draftId ? draft.data?.content : source.data?.content;
  useEffect(() => { if (text === undefined && original !== undefined) setText(original); }, [original, text]);

  // validate while typing, after a short pause
  const [settled, setSettled] = useState<string>();
  useEffect(() => { const t = setTimeout(() => setSettled(text), 350); return () => clearTimeout(t); }, [text]);
  const check = useQuery({
    queryKey: ["pipe-validate", pid, settled],
    queryFn: () => unwrap(api.POST("/projects/{pid}/pipeline/validate", { params: { path: { pid } }, body: { content: settled! } })),
    enabled: settled !== undefined, placeholderData: (prev) => prev,
  });
  const findings = check.data?.findings ?? [];
  const errors = findings.filter((f) => f.severity === "error");
  const pipes = check.data?.pipelines ?? [];
  const pipe = pipes.find((p) => p.name === pipeName) ?? pipes[0];
  const step = pipe?.steps.find((s) => s.id === stepId) ?? pipe?.steps[0];
  const badLines = useMemo(() => errors.map((f) => lineOf(f, text ?? "")).filter((n): n is number => n !== undefined), [errors, text]);

  const status = draft.data?.status ?? "new";
  const editable = !draftId || status === "draft";
  const stale = text !== settled || check.isFetching;
  const dirty = text !== undefined && text !== original;

  const save = useMutation({
    mutationFn: async () => {
      if (draftId) return unwrap(api.PUT("/projects/{pid}/pipeline/drafts/{draft_id}", { params: { path: { pid, draft_id: draftId } }, body: { content: text! }, headers: csrfHeader() }));
      return unwrap(api.POST("/projects/{pid}/pipeline/drafts", { params: { path: { pid } }, body: { content: text! }, headers: csrfHeader() }));
    },
    onSuccess: (d) => { void qc.invalidateQueries({ queryKey: ["pipe-draft"] }); void qc.invalidateQueries({ queryKey: ["pipe-drafts", pid] }); if (!draftId) go(`/p/${pid}/pipeline/edit/${d.id}`); },
  });
  const propose = useMutation({
    mutationFn: async () => {
      if (dirty || !draftId) throw new Error("Save the draft before proposing it.");
      const r = await api.POST("/projects/{pid}/pipeline/drafts/{draft_id}/propose", { params: { path: { pid, draft_id: draftId } }, headers: csrfHeader() });
      if (r.response.status === 409 && r.error && "diff" in (r.error as object)) {
        const e = r.error as unknown as { diff: string; detail: string };
        setConflict({ diff: e.diff });
        throw new Error(e.detail);
      }
      if (r.error !== undefined || !r.data) throw new Error((r.error as { detail?: string } | undefined)?.detail ?? "Could not propose the change");
      return r.data;
    },
    onSuccess: () => { setConflict(null); void qc.invalidateQueries({ queryKey: ["pipe-draft"] }); },
  });

  const loadError = (draftId ? draft.error : source.error)?.message;
  const alone = errors.length > 0 ? "Fix the errors first" : stale ? "Checking…" : dirty ? "Save the draft first" : "";

  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid} / <Link to={`/p/${pid}/pipeline`} go={go}>Pipeline</Link> / Edit</p>
      <div className="page-head">
        <div><h1>Edit pipeline</h1>
          <p>Changes are kept as a draft. Nothing reaches git until you propose them, and then only as a change request someone else approves.</p></div>
        <div className="draft-state" role="status">
          <span>{status === "new" ? "Not saved yet" : `Draft ${draftId}`}</span>
          {draft.data && <Chip state={status === "applied" ? "ok" : status === "proposed" ? "wait" : status === "closed" ? "stop" : "idle"}>
            {status === "draft" ? "Draft" : status === "proposed" ? "Waiting for review" : status === "applied" ? "Merged" : "Closed"}</Chip>}
          {draft.data?.base_sha && <span className="mono">based on {draft.data.base_sha.slice(0, 8)}</span>}
        </div>
      </div>
      {loadError && <p role="alert">Could not load the pipeline file: {loadError}</p>}
      {text !== undefined && (
        <article className="sheet" aria-label="Pipeline editor">
          <div className="section">
            <h3>Flow</h3>
            {pipes.length > 1 && (
              <form className="quiet-form" onSubmit={(e) => e.preventDefault()} aria-label="Choose pipeline">
                <label className="soft" htmlFor="pe">Pipeline</label>
                <select className="field" id="pe" value={pipe?.name} onChange={(e) => { setPipeName(e.target.value); setStepId(undefined); }}>
                  {pipes.map((p) => <option key={p.name}>{p.name}</option>)}
                </select>
              </form>
            )}
            {pipe ? <PipelineGraph steps={pipe.steps} current={step?.id} onPick={setStepId} /> : <p className="source-note">The flow appears once the file parses.</p>}
          </div>
          <div className="pipe-grid">
            <div className="section">
              <h3>Step inspector</h3>
              {step ? (
                <>
                  <h4 className="inspector-title">{step.id}</h4>
                  <dl className="fields">
                    <dt>Agent</dt><dd className="mono">{step.agent ?? "none"}</dd>
                    <dt>Depends on</dt><dd className="mono">{step.depends_on.join(", ") || "nothing"}</dd>
                    <dt>Requires</dt><dd className="mono">{step.requires.join(", ") || "nothing"}</dd>
                    <dt>Produces</dt><dd className="mono">{step.produces.join(", ") || "nothing"}</dd>
                    <dt>Gate</dt><dd>{step.gate_role ? `signed by ${step.gate_role}` : "no human gate"}</dd>
                  </dl>
                </>
              ) : <p className="source-note">Pick a step in the flow.</p>}
              <h3>Checks</h3>
              {findings.length === 0 ? (
                <ul className="checks"><li data-state={stale ? "wait" : "ok"}><span className="sym" aria-hidden="true">{stale ? "…" : "✓"}</span>
                  <span className="what"><b>{stale ? "Checking" : "No problems found"}</b></span><Chip state={stale ? "wait" : "ok"}>{stale ? "Checking" : "Valid"}</Chip></li></ul>
              ) : (
                <ul className="checks">
                  {findings.map((f, i) => (
                    <li key={i} data-state={f.severity === "error" ? "bad" : "wait"}>
                      <span className="sym" aria-hidden="true">{f.severity === "error" ? "✕" : "!"}</span>
                      <span className="what"><b>{f.message}</b><span className="mono">{f.code}{f.path ? ` · ${f.path}` : ""}</span></span>
                      <Chip state={f.severity === "error" ? "bad" : "wait"}>{f.severity === "error" ? "Error" : "Warning"}</Chip>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="section">
              <h3>asac.yaml</h3>
              <YamlEditor value={text} onChange={setText} badLines={badLines} readOnly={!editable} label="asac.yaml source" />
              {!editable && <p className="source-note">This draft is {status}. Start a new edit to change the file again.</p>}
            </div>
          </div>
          <div className="section">
            <h3>Changes</h3>
            <Diff text={dirty || draftId ? (draft.data && !dirty ? draft.data.diff : localDiff(original ?? "", text)) : ""} />
            {conflict && (
              <div role="alert">
                <p><b>The default branch changed this file since your draft was based on it.</b> Copy your edits, start a new edit from the current file and apply them again. Upstream changes:</p>
                <Diff text={conflict.diff} />
              </div>
            )}
            {draft.data?.change_request_url && <p>Change request: <a href={draft.data.change_request_url} rel="noreferrer noopener" target="_blank">{draft.data.change_request_url}</a></p>}
            {(save.error || propose.error) && !conflict && <p role="alert">{(save.error ?? propose.error)!.message}</p>}
          </div>
          <div className="section pipe-foot">
            <button className="btn" type="button" disabled={!editable || !dirty || save.isPending} onClick={() => save.mutate()}>{draftId ? "Save draft" : "Save as draft"}</button>
            <button className="btn btn-primary" type="button" disabled={!draftId || !editable || errors.length > 0 || stale || dirty || propose.isPending} onClick={() => propose.mutate()}>Propose change</button>
            {editable && alone && <span className="alone">{alone}</span>}
          </div>
        </article>
      )}
      <article className="sheet" aria-label="Drafts"><DraftsList pid={pid} go={go} current={draftId} /></article>
    </>
  );
}

/** Line diff for the unsaved text; the saved draft diff comes from the server. */
function localDiff(a: string, b: string): string {
  if (a === b) return "";
  const x = a.split("\n"), y = b.split("\n");
  const out: string[] = [];
  const n = Math.max(x.length, y.length);
  for (let i = 0; i < n; i++) {
    if (x[i] === y[i]) continue;
    if (x[i] !== undefined) out.push(`-${x[i]}`);
    if (y[i] !== undefined) out.push(`+${y[i]}`);
  }
  return out.join("\n");
}
