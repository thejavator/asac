import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Save, Archive, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Field, FormActions } from "../components/app/Form";
import { Crumbs, Empty, ErrorAlert, Page, PageHeader, TableCard } from "../components/app/Page";
import { StatusBadge } from "../components/StatusBadge";

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
    <section aria-labelledby="proj-h" className="grid gap-6">
      {q.isError && <ErrorAlert title="Could not load projects">{q.error.message}</ErrorAlert>}
      {q.isPending && <Skeleton className="h-40" />}
      {q.data && (
        <TableCard title={<span id="proj-h">Projects</span>} description={`${q.data.length} project${q.data.length === 1 ? "" : "s"}`}>
          {q.data.length === 0 ? <div className="p-6"><Empty>No project yet. Create the first one below.</Empty></div> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Project</TableHead><TableHead className="hidden md:table-cell">Manifest</TableHead>
                  <TableHead>Groups that see it</TableHead><TableHead>Status</TableHead><TableHead className="pr-6 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {q.data.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="pl-6">
                      <div className="font-medium">{p.name}</div>
                      <div className="font-mono text-xs text-muted-foreground">{p.id}</div>
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs md:table-cell">{p.manifest}</TableCell>
                    <TableCell className="font-mono text-xs">{p.access.join(", ") || "everyone signed in"}</TableCell>
                    <TableCell>{p.archived ? <StatusBadge state="idle">Archived</StatusBadge> : <StatusBadge state="ok">Active</StatusBadge>}</TableCell>
                    <TableCell className="pr-6 text-right whitespace-nowrap">
                      <Button variant="outline" size="sm" onClick={() => { setEditing(p.id); setForm({ id: p.id, name: p.name, manifest: p.manifest, team: p.team ?? "", repo: p.repo ?? "", access: p.access.join(", ") }); }}>
                        <Pencil /> Edit
                      </Button>{" "}
                      <Button variant="ghost" size="sm" disabled={archive.isPending} onClick={() => archive.mutate(p)}>
                        {p.archived ? <><RotateCcw /> Restore</> : <><Archive /> Archive</>}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TableCard>
      )}
      <Card>
        <CardHeader>
          <CardTitle>{editing ? `Edit ${editing}` : "Create a project"}</CardTitle>
          <CardDescription>{editing ? "Changes are audited." : "Each change is audited."}</CardDescription>
        </CardHeader>
        <CardContent>
          <form aria-label={editing ? "Edit project" : "Create project"} className="grid gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <div className="grid gap-4 sm:grid-cols-2">
              {!editing && (
                <Field id="p-id" label="Identifier" hint="Lower case, digits and dashes.">
                  <Input id="p-id" required pattern="[a-z][a-z0-9\-]{0,40}" className="font-mono" value={form.id} onChange={set("id")} />
                </Field>
              )}
              <Field id="p-name" label="Name"><Input id="p-name" required value={form.name} onChange={set("name")} /></Field>
              <Field id="p-manifest" label="Path of asac.yaml on the portal server" className="sm:col-span-2">
                <Input id="p-manifest" required className="font-mono" value={form.manifest} onChange={set("manifest")} />
              </Field>
              <Field id="p-team" label="Team"><Input id="p-team" value={form.team} onChange={set("team")} /></Field>
              <Field id="p-repo" label="Repository URL"><Input id="p-repo" value={form.repo} onChange={set("repo")} /></Field>
              <Field id="p-access" label="Groups that can see it" className="sm:col-span-2"
                hint="Comma separated. Empty means everyone signed in.">
                <Input id="p-access" value={form.access} onChange={set("access")} />
              </Field>
            </div>
            {err && <ErrorAlert title="Could not save">{err.message}</ErrorAlert>}
            <FormActions>
              <Button type="submit" disabled={save.isPending}>{editing ? <><Save /> Save changes</> : <><Plus /> Create project</>}</Button>
              {editing && <Button type="button" variant="ghost" onClick={() => { setEditing(null); setForm(EMPTY); }}><X /> Cancel</Button>}
            </FormActions>
          </form>
        </CardContent>
      </Card>
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
    <Card aria-labelledby="org-h">
      <CardHeader>
        <CardTitle id="org-h">Organisation</CardTitle>
        <CardDescription>Applies to every project.</CardDescription>
      </CardHeader>
      <CardContent>
        <form aria-label="Organisation" className="grid gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="o-name" label="Name"><Input id="o-name" required value={name ?? q.data.name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field id="o-roles" label="Groups that see every project" hint="Comma separated.">
              <Input id="o-roles" value={roles ?? (q.data.org_roles ?? []).join(", ")} onChange={(e) => setRoles(e.target.value)} />
            </Field>
          </div>
          {save.error && <ErrorAlert title="Could not save">{save.error.message}</ErrorAlert>}
          <FormActions><Button type="submit" disabled={save.isPending}><Save /> Save organisation</Button></FormActions>
        </form>
      </CardContent>
    </Card>
  );
}

export function AdminPage({ go }: { go: (to: string) => void }) {
  const users = useQuery({ queryKey: ["admin-users"], queryFn: () => unwrap(api.GET("/admin/users")) });
  const events = useQuery({ queryKey: ["admin-events"], queryFn: () => unwrap(api.GET("/admin/events")) });
  return (
    <Page>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: "Administration" }]} />
      <PageHeader title="Administration" description="Projects, organisation, people who have signed in, and every change made in the portal. Organisation admins only." />
      <ProjectsAdmin />
      <OrganizationAdmin />
      {users.isError && <ErrorAlert title="Could not load people">{users.error.message}</ErrorAlert>}
      {users.data && (
        <TableCard title="People" description="Everyone who has signed in, and the groups they came with.">
          {users.data.length === 0 ? <div className="p-6"><Empty>Nobody has signed in yet.</Empty></div> : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-6">Name</TableHead><TableHead className="hidden md:table-cell">Subject</TableHead><TableHead>Groups</TableHead><TableHead className="hidden pr-6 md:table-cell">Last sign-in</TableHead></TableRow></TableHeader>
              <TableBody>
                {users.data.map((u) => (
                  <TableRow key={u.subject}>
                    <TableCell className="pl-6 font-medium">{u.name}</TableCell>
                    <TableCell className="hidden font-mono text-xs md:table-cell">{u.subject}</TableCell>
                    <TableCell className="font-mono text-xs">{u.claims.join(", ") || "none"}</TableCell>
                    <TableCell className="hidden pr-6 font-mono text-xs text-muted-foreground md:table-cell">{u.last_login}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TableCard>
      )}
      {events.data && (
        <TableCard title="Access changes" description="Every change to projects, organisation and access, newest first.">
          {events.data.length === 0 ? <div className="p-6"><Empty>No change yet.</Empty></div> : (
            <Table>
              <TableHeader><TableRow><TableHead className="hidden pl-6 md:table-cell">When</TableHead><TableHead>Who</TableHead><TableHead>Action</TableHead><TableHead className="pr-6">Detail</TableHead></TableRow></TableHeader>
              <TableBody>
                {events.data.map((e) => (
                  <TableRow key={e.seq}>
                    <TableCell className="hidden pl-6 font-mono text-xs text-muted-foreground md:table-cell">{e.at}</TableCell>
                    <TableCell>{e.actor}</TableCell>
                    <TableCell className="font-mono text-xs">{e.action}</TableCell>
                    <TableCell className="max-w-md pr-6 whitespace-normal break-words">{e.detail}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TableCard>
      )}
          </Page>
  );
}
