import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmButton } from "../components/app/ConfirmButton";
import { Field, FormActions } from "../components/app/Form";
import { Crumbs, Empty, ErrorAlert, Page, PageHeader, TableCard } from "../components/app/Page";

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
    <Page>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid, to: `/p/${pid}/runs` }, { label: "Access" }]} />
      <PageHeader title="Access" description="Which identity-provider groups get which role in this project. A group listed here can also see the project." />
      {q.isError && <ErrorAlert title="Could not load access">{q.error.message}</ErrorAlert>}
      {q.isPending && <Skeleton className="h-40" />}
      {q.data && (
        <TableCard title="Groups and roles">
          {q.data.length === 0 ? <div className="p-6"><Empty>No group has a role yet. Add one below.</Empty></div> : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-6">Group</TableHead><TableHead>Role</TableHead><TableHead className="pr-6 text-right">Actions</TableHead></TableRow></TableHeader>
              <TableBody>
                {q.data.map((m) => (
                  <TableRow key={`${m.claim}/${m.role}`}>
                    <TableCell className="pl-6 font-mono text-xs">{m.claim}</TableCell>
                    <TableCell><Badge variant="secondary">{m.role}</Badge></TableCell>
                    <TableCell className="pr-6 text-right">
                      <ConfirmButton
                        label="Remove"
                        title={`Remove ${m.role} from ${m.claim}?`}
                        description="People in this group lose this role in the project. The change is audited."
                        confirm="Remove role"
                        disabled={remove.isPending}
                        onConfirm={() => remove.mutate(m)}
                      />
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
          <CardTitle>Give a group a role</CardTitle>
          <CardDescription>Project owner or organisation admin only. Each change is audited.</CardDescription>
        </CardHeader>
        <CardContent>
          <form aria-label="Give a group a role" className="grid gap-4" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_14rem]">
              <Field id="claim" label="Group name from the identity provider">
                <Input id="claim" required value={claim} onChange={(e) => setClaim(e.target.value)} className="font-mono" />
              </Field>
              <Field id="role" label="Role">
                <Select value={role} onValueChange={(v) => setRole(v as typeof role)}>
                  <SelectTrigger id="role" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>{ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
            </div>
            {err && <ErrorAlert title="Could not save">{err.message}</ErrorAlert>}
            <FormActions><Button type="submit" disabled={add.isPending}><Plus /> Add role</Button></FormActions>
          </form>
        </CardContent>
      </Card>
    </Page>
  );
}
