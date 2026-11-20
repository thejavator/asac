import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Chip } from "../components/Chip";
import { Link } from "../components/Link";

type ProjectForm = { id: string; name: string; manifest: string; team: string; repo: string; access: string };
const EMPTY: ProjectForm = { id: "", name: "", manifest: "", team: "", repo: "", access: "" };
const groups = (text: string) => text.split(",").map((g) => g.trim()).filter(Boolean);

function ProjectsAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-projects"], queryFn: () => unwrap(api.GET("/admin/projects")) });
  const [form, setForm] = useState<ProjectForm>(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["admin-projects"] });
    void qc.invalidateQueries({ queryKey: ["admin-events"] });
    void qc.invalidateQueries({ queryKey: ["projects"] });
  };
  const save = useMutation({
    mutationFn: () => {
      const body = { name: form.name, manifest: form.manifest, team: form.team || null, repo: form.repo || null, access: groups(form.access) };
      return editing
        ? unwrap(api.PUT("/admin/projects/{pid}", { params: { path: { pid: editing } }, body, headers: csrfHeader() }))
        : unwrap(api.POST("/admin/projects", { body: { id: form.id, ...body }, headers: csrfHeader() }));
    },
    onSuccess: () => { setForm(EMPTY); setEditing(null); refresh(); },
  });
  const archive = useMutation({
    mutationFn: async (p: { id: string; archived: boolean }) => {
      const path = p.archived ? "/admin/projects/{pid}/restore" : "/admin/projects/{pid}/archive";
      const r = await api.POST(path, { params: { path: { pid: p.id } }, headers: csrfHeader() });
      if (!r.response.ok) throw new Error("Could not change the project");
    },
    onSuccess: refresh,
  });
  const set = (k: keyof ProjectForm) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const err = save.error ?? archive.error;
  return (
    <section aria-labelledby="proj-h">
      <h2 id="proj-h">Projects</h2>
      {q.isError && <p role="alert">{q.error.message}</p>}
      {q.data && (
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>Project</th><th className="hide-sm">Manifest</th><th>Groups that see it</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {q.data.length === 0 && <tr><td colSpan={5} className="soft">No project yet. Create the first one below.</td></tr>}
            {q.data.map((p) => (
              <tr key={p.id}>
                <td>{p.name}<br /><span className="mono soft">{p.id}</span></td>
                <td className="mono hide-sm">{p.manifest}</td>
                <td className="mono">{p.access.join(", ") || "everyone signed in"}</td>
                <td>{p.archived ? <Chip state="idle">Archived</Chip> : <Chip state="ok">Active</Chip>}</td>
                <td>
                  <button className="btn" type="button" onClick={() => { setEditing(p.id); setForm({ id: p.id, name: p.name, manifest: p.manifest, team: p.team ?? "", repo: p.repo ?? "", access: p.access.join(", ") }); }}>Edit</button>{" "}
                  <button className="btn" type="button" onClick={() => archive.mutate(p)}>{p.archived ? "Restore" : "Archive"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      <form className="sheet decide" aria-label={editing ? "Edit project" : "Create project"} onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <h3>{editing ? `Edit ${editing}` : "Create a project"}</h3>
        {!editing && <p><label htmlFor="p-id">Identifier (lower case, digits, dashes)</label><br />
          <input className="field" id="p-id" required pattern="[a-z][a-z0-9\-]{0,40}" value={form.id} onChange={set("id")} /></p>}
        <p><label htmlFor="p-name">Name</label><br /><input className="field" id="p-name" required value={form.name} onChange={set("name")} /></p>
        <p><label htmlFor="p-manifest">Path of asac.yaml on the portal server</label><br />
          <input className="field mono" id="p-manifest" required value={form.manifest} onChange={set("manifest")} /></p>
        <p><label htmlFor="p-team">Team</label><br /><input className="field" id="p-team" value={form.team} onChange={set("team")} /></p>
        <p><label htmlFor="p-repo">Repository URL</label><br /><input className="field" id="p-repo" value={form.repo} onChange={set("repo")} /></p>
        <p><label htmlFor="p-access">Groups that can see it (comma separated, empty means everyone signed in)</label><br />
          <input className="field" id="p-access" value={form.access} onChange={set("access")} /></p>
        {err && <p role="alert" className="notice"><span aria-hidden="true">⚠</span><span>{err.message}</span></p>}
        <div className="actions">
          <button className="btn btn-primary" type="submit" disabled={save.isPending}>{editing ? "Save changes" : "Create project"}</button>
          {editing && <button className="btn" type="button" onClick={() => { setEditing(null); setForm(EMPTY); }}>Cancel</button>}
        </div>
      </form>
    </section>
  );
}

function OrganizationAdmin() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-org"], queryFn: () => unwrap(api.GET("/admin/organization")) });
  const [name, setName] = useState<string | null>(null);
  const [roles, setRoles] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/admin/organization", {
      body: { name: name ?? q.data?.name ?? "", org_roles: groups(roles ?? q.data?.org_roles?.join(",") ?? "") }, headers: csrfHeader(),
    })),
    onSuccess: () => { setName(null); setRoles(null); void qc.invalidateQueries(); },
  });
  if (!q.data) return null;
  return (
    <section aria-labelledby="org-h">
      <h2 id="org-h">Organisation</h2>
      <form className="sheet decide" aria-label="Organisation" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <p><label htmlFor="o-name">Name</label><br />
          <input className="field" id="o-name" required value={name ?? q.data.name} onChange={(e) => setName(e.target.value)} /></p>
        <p><label htmlFor="o-roles">Groups that see every project (comma separated)</label><br />
          <input className="field" id="o-roles" value={roles ?? (q.data.org_roles ?? []).join(", ")} onChange={(e) => setRoles(e.target.value)} /></p>
        {save.error && <p role="alert" className="notice"><span aria-hidden="true">⚠</span><span>{save.error.message}</span></p>}
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={save.isPending}>Save organisation</button></div>
      </form>
    </section>
  );
}

export function AdminPage({ go }: { go: (to: string) => void }) {
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => unwrap(api.GET("/admin/users")) });
  const events = useQuery({ queryKey: ["admin-events"], queryFn: () => unwrap(api.GET("/admin/events")) });
  return (
    <>
      <p className="crumbs"><Link to="/" go={go}>All projects</Link> / Administration</p>
      <div className="page-head"><div><h1>Administration</h1>
        <p>Projects, organisation, people who have signed in, and every change made in the portal. Organisation admins only.</p></div></div>
      <ProjectsAdmin />
      <OrganizationAdmin />
      {users.isError && <p role="alert">{users.error.message}</p>}
      {users.data && (
        <section aria-labelledby="users-h">
          <h2 id="users-h">People</h2>
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>Name</th><th className="hide-sm">Subject</th><th>Groups</th><th className="hide-sm">Last sign-in</th></tr></thead>
            <tbody>{users.data.map((u) => (
              <tr key={u.subject}><td>{u.name}</td><td className="mono hide-sm">{u.subject}</td>
                <td className="mono">{u.claims.join(", ") || "none"}</td><td className="mono hide-sm">{u.last_login}</td></tr>
            ))}</tbody>
          </table></div>
        </section>
      )}
      {events.data && (
        <section aria-labelledby="ev-h">
          <h2 id="ev-h">Access changes</h2>
          {events.data.length === 0 ? <p className="soft">No change yet.</p> : (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th className="hide-sm">When</th><th>Who</th><th>Action</th><th>Detail</th></tr></thead>
              <tbody>{events.data.map((e) => (
                <tr key={e.seq}><td className="mono hide-sm">{e.at}</td><td>{e.actor}</td><td className="mono">{e.action}</td><td>{e.detail}</td></tr>
              ))}</tbody>
            </table></div>
          )}
        </section>
      )}
    </>
  );
}
