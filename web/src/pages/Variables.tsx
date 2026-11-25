import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Save } from "lucide-react";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmButton } from "../components/app/ConfirmButton";
import { Field, FormActions } from "../components/app/Form";
import { Code, Crumbs, Empty, ErrorAlert, Page, PageHeader, TableCard } from "../components/app/Page";
import { StatusBadge } from "../components/StatusBadge";

export function VariablesPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["vars", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/variables", { params: { path: { pid } } })) });
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [probe, setProbe] = useState<Record<string, { ok: boolean; text: string }>>({});
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
      setProbe((p) => ({ ...p, [k]: { ok: r.ok, text: `${r.ok ? "Reachable" : "Not reachable"}: ${r.detail}` } }));
    },
  });
  const err = save.error ?? del.error ?? test.error;
  const isUrl = (v: string) => /^https?:\/\//.test(v);
  return (
    <Page>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid, to: `/p/${pid}/runs` }, { label: "Variables" }]} />
      <PageHeader
        title="Variables"
        description={<>Project URLs and settings, kept in <Code>asac.vars.yaml</Code>. Secrets are never stored here: a secret key only accepts a vault reference such as <Code>{"${vault.path}"}</Code>.</>}
      />
      <Alert role="note">
        <Info />
        <AlertTitle>Keys the integrations read</AlertTitle>
        <AlertDescription className="grid gap-1.5">
          <p>Pipeline editing: <Code>forge_kind</Code> (git, github or gitlab), <Code>forge_repo</Code>, <Code>forge_token</Code> (vault reference) and optionally <Code>forge_api</Code> (https only).</p>
          <p>Ticket links: <Code>tracker_kind</Code> (jira, github or gitlab), <Code>tracker_url</Code>, <Code>tracker_token</Code> and, for GitHub or GitLab, <Code>tracker_project</Code>.</p>
          <p>Wiki pages: <Code>wiki_kind</Code> (confluence or gitlab), <Code>wiki_url</Code>, <Code>wiki_token</Code> and <Code>wiki_space</Code> or <Code>wiki_project</Code>.</p>
        </AlertDescription>
      </Alert>
      {q.isError && <ErrorAlert title="Could not load variables">{q.error.message}</ErrorAlert>}
      {q.isPending && <Skeleton className="h-40" />}
      {q.data && (
        <TableCard title="Variables">
          {q.data.length === 0 ? <div className="p-6"><Empty>No variables yet. Add the first one below.</Empty></div> : (
            <Table>
              <TableHeader><TableRow><TableHead className="pl-6">Key</TableHead><TableHead>Value</TableHead><TableHead>Kind</TableHead><TableHead className="pr-6 text-right">Actions</TableHead></TableRow></TableHeader>
              <TableBody>
                {q.data.map((v) => (
                  <TableRow key={v.key}>
                    <TableCell className="pl-6 font-mono text-xs font-medium">{v.key}</TableCell>
                    <TableCell className="max-w-sm font-mono text-xs break-all whitespace-normal">
                      {v.value}
                      {probe[v.key] && (
                        <div role="status" className={probe[v.key]!.ok ? "mt-1 text-success" : "mt-1 text-destructive"}>{probe[v.key]!.text}</div>
                      )}
                    </TableCell>
                    <TableCell>{v.secret ? <StatusBadge state="stop">Vault reference</StatusBadge> : <StatusBadge state="idle">Plain</StatusBadge>}</TableCell>
                    <TableCell className="pr-6 text-right whitespace-nowrap">
                      {!v.secret && isUrl(v.value) && (
                        <Button variant="outline" size="sm" disabled={test.isPending} onClick={() => test.mutate(v.key)}>Test</Button>
                      )}{" "}
                      <ConfirmButton
                        label="Delete"
                        title={`Delete ${v.key}?`}
                        description="The change is audited and cannot be undone from this page."
                        confirm="Delete variable"
                        disabled={del.isPending}
                        onConfirm={() => del.mutate(v.key)}
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
          <CardTitle>Add or change a variable</CardTitle>
          <CardDescription>Owner or admin only. Each change is audited.</CardDescription>
        </CardHeader>
        <CardContent>
          <form aria-label="Set a variable" className="grid gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <div className="grid gap-4 sm:grid-cols-[16rem_minmax(0,1fr)]">
              <Field id="vkey" label="Key"><Input id="vkey" required className="font-mono" value={key} onChange={(e) => setKey(e.target.value)} /></Field>
              <Field id="vval" label="Value"><Input id="vval" required maxLength={2000} className="font-mono" value={value} onChange={(e) => setValue(e.target.value)} /></Field>
            </div>
            {err && <ErrorAlert title="Could not save">{err.message}</ErrorAlert>}
            <FormActions><Button type="submit" disabled={save.isPending}><Save /> Save variable</Button></FormActions>
          </form>
        </CardContent>
      </Card>
    </Page>
  );
}
