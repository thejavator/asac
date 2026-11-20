import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Link } from "../components/Link";

const ROLES = ["owner", "product_owner", "qa", "developer", "reader"] as const;

export function AccessPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["mappings", pid],
    queryFn: () => unwrap(api.GET("/projects/{pid}/mappings", { params: { path: { pid } } })),
  });
  const [claim, setClaim] = useState("");
  const [role, setRole] = useState<(typeof ROLES)[number]>("reader");
  const refresh = () => qc.invalidateQueries({ queryKey: ["mappings", pid] });
  const add = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/projects/{pid}/mappings", { params: { path: { pid } }, body: { claim, role }, headers: csrfHeader() })),
    onSuccess: () => { setClaim(""); void refresh(); },
  });
  const remove = useMutation({
    mutationFn: async (m: { claim: string; role: string }) => {
      const r = await api.DELETE("/projects/{pid}/mappings/{claim}/{role}", {
        params: { path: { pid, claim: m.claim, role: m.role } }, headers: csrfHeader(),
      });
      if (!r.response.ok) throw new Error("Could not remove the mapping");
    },
    onSuccess: () => void refresh(),
  });
  const err = add.error ?? remove.error;
  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / {pid} / Access</p>
      <div className="page-head"><div><h1>Access</h1>
        <p>Which identity-provider groups get which role in this project. A group listed here can also see the project.</p></div></div>
      {q.isError && <p role="alert">{q.error.message}</p>}
      {q.data && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Group</th><th>Role</th><th>Actions</th></tr></thead>
            <tbody>
              {q.data.length === 0 && <tr><td colSpan={3} className="soft">No group has a role yet. Add one below.</td></tr>}
              {q.data.map((m) => (
                <tr key={`${m.claim}/${m.role}`}>
                  <td className="mono">{m.claim}</td><td>{m.role}</td>
                  <td><button className="btn btn-danger" type="button" onClick={() => remove.mutate(m)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form className="sheet decide" aria-label="Give a group a role" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <h3>Give a group a role</h3>
        <p><label htmlFor="claim">Group name from the identity provider</label><br />
          <input className="field" id="claim" required value={claim} onChange={(e) => setClaim(e.target.value)} /></p>
        <p><label htmlFor="role">Role</label><br />
          <select className="field" id="role" value={role} onChange={(e) => setRole(e.target.value as typeof role)}>
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select></p>
        {err && <p role="alert" className="notice"><span aria-hidden="true">⚠</span><span>{err.message}</span></p>}
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={add.isPending}>Add role</button>
          <span className="alone">Project owner or organisation admin only. Each change is audited.</span></div>
      </form>
    </>
  );
}
