import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Chip } from "../components/Chip";
import { Link } from "../components/Link";

export function VariablesPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["vars", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/variables", { params: { path: { pid } } })) });
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [probe, setProbe] = useState<Record<string, string>>({});
  const refresh = () => qc.invalidateQueries({ queryKey: ["vars", pid] });
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/projects/{pid}/variables/{key}", { params: { path: { pid, key } }, body: { value }, headers: csrfHeader() })),
    onSuccess: () => { setKey(""); setValue(""); void refresh(); },
  });
  const del = useMutation({
    mutationFn: async (k: string) => {
      const r = await api.DELETE("/projects/{pid}/variables/{key}", { params: { path: { pid, key: k } }, headers: csrfHeader() });
      if (!r.response.ok) throw new Error("Could not delete the variable");
    },
    onSuccess: () => void refresh(),
  });
  const test = useMutation({
    mutationFn: async (k: string) => {
      const r = await unwrap(api.POST("/projects/{pid}/connections/test", { params: { path: { pid } }, body: { key: k }, headers: csrfHeader() }));
      setProbe((p) => ({ ...p, [k]: `${r.ok ? "Reachable" : "Not reachable"}: ${r.detail}` }));
    },
  });
  const err = save.error ?? del.error ?? test.error;
  const isUrl = (v: string) => /^https?:\/\//.test(v);
  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid} / Variables</p>
      <div className="page-head"><div><h1>Variables</h1>
        <p>Project URLs and settings, kept in <span className="mono">asac.vars.yaml</span>. Secrets are never stored here: a secret key only accepts a vault reference such as <span className="mono">${"{vault.path}"}</span>.</p></div></div>
      <p className="source-note">Pipeline editing needs <span className="mono">forge_kind</span> (git, github or gitlab), <span className="mono">forge_repo</span>, <span className="mono">forge_token</span> (vault reference) and optionally <span className="mono">forge_api</span> (https only).</p>
      <p className="source-note">Ticket links need <span className="mono">tracker_kind</span> (jira, github or gitlab), <span className="mono">tracker_url</span>, <span className="mono">tracker_token</span> and, for GitHub or GitLab, <span className="mono">tracker_project</span>. Wiki pages need <span className="mono">wiki_kind</span> (confluence or gitlab), <span className="mono">wiki_url</span>, <span className="mono">wiki_token</span> and <span className="mono">wiki_space</span> or <span className="mono">wiki_project</span>.</p>
      {q.isError && <p role="alert">Could not load variables: {q.error.message}</p>}
      {q.data && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Key</th><th>Value</th><th>Kind</th><th>Actions</th></tr></thead>
            <tbody>
              {q.data.length === 0 && <tr><td colSpan={4} className="soft">No variables yet. Add the first one below.</td></tr>}
              {q.data.map((v) => (
                <tr key={v.key}>
                  <td className="mono">{v.key}</td><td className="mono">{v.value}</td>
                  <td>{v.secret ? <Chip state="stop">Vault reference</Chip> : <Chip state="idle">Plain</Chip>}</td>
                  <td>
                    {!v.secret && isUrl(v.value) && <button className="btn" type="button" onClick={() => test.mutate(v.key)}>Test</button>}{" "}
                    <button className="btn btn-danger" type="button" onClick={() => del.mutate(v.key)}>Delete</button>
                    {probe[v.key] && <div className="soft" role="status">{probe[v.key]}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form className="sheet decide" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} aria-label="Set a variable">
        <h3>Add or change a variable</h3>
        <p><label htmlFor="vkey">Key</label><br /><input className="field" id="vkey" required value={key} onChange={(e) => setKey(e.target.value)} /></p>
        <p><label htmlFor="vval">Value</label><br /><input className="field" id="vval" required maxLength={2000} value={value} onChange={(e) => setValue(e.target.value)} /></p>
        {err && <p role="alert" className="notice"><span aria-hidden="true">⚠</span><span>{err.message}</span></p>}
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={save.isPending}>Save variable</button>
          <span className="alone">Owner or admin only. Each change is audited.</span></div>
      </form>
    </>
  );
}
