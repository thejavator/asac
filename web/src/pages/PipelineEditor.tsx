import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, csrfHeader, unwrap, type Schema } from "../api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { Field, FormActions } from "../components/app/Form";
import { Code, Crumbs, Empty, ErrorAlert, Fields, Hint, Output, Page, PageHeader } from "../components/app/Page";
import { DefinitionFlow } from "../components/app/StepNode";
import { Link } from "../components/Link";
import { PipelineGraph } from "../components/PipelineGraph";
import { StatusBadge } from "../components/StatusBadge";
import { YamlEditor } from "../components/YamlEditor";

type Finding = Schema["FindingOut"];

const lineOf = (f: Finding, text: string): number | undefined => {
  // findings carry a YAML path such as pipelines.feature.steps.review; point at its last key
  const last = f.path.split(".").filter(Boolean).pop();
  if (!last) return undefined;
  const i = text.split("\n").findIndex((l) => l.includes(`${last}:`));
  return i >= 0 ? i + 1 : undefined;
};

const STATUS: Record<string, { state: "idle" | "wait" | "ok" | "stop"; label: string }> = {
  draft: { state: "idle", label: "Draft" },
  proposed: { state: "wait", label: "Waiting for review" },
  applied: { state: "ok", label: "Merged" },
  closed: { state: "stop", label: "Closed" },
};

function DraftsList({ pid, go, current }: { pid: string; go: (to: string) => void; current?: string }) {
  const q = useQuery({ queryKey: ["pipe-drafts", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/pipeline/drafts", { params: { path: { pid } } })) });
  if (q.isError) return <ErrorAlert title="Could not load drafts">{q.error.message}</ErrorAlert>;
  if (!q.data) return <Skeleton className="h-24" />;
  if (q.data.length === 0) return <Empty>No drafts yet. Save your first edit to create one.</Empty>;
  return (
    <Table>
      <TableHeader>
        <TableRow><TableHead className="pl-6">Draft</TableHead><TableHead>Author</TableHead><TableHead>Updated</TableHead><TableHead>Status</TableHead><TableHead className="pr-6">Change request</TableHead></TableRow>
      </TableHeader>
      <TableBody>
        {q.data.map((d) => {
          const s = STATUS[d.status] ?? { state: "idle" as const, label: d.status };
          return (
            <TableRow key={d.id} data-current={d.id === current || undefined} className={cn(d.id === current && "bg-accent")}>
              <TableCell className="pl-6 font-mono text-xs"><Link to={`/p/${pid}/pipeline/edit/${d.id}`} go={go} className="underline-offset-4 hover:underline">{d.id}</Link></TableCell>
              <TableCell>{d.author}</TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">{d.updated_at}</TableCell>
              <TableCell><StatusBadge state={s.state}>{s.label}</StatusBadge></TableCell>
              <TableCell className="pr-6">
                {d.change_request_url
                  ? <a className="underline-offset-4 hover:underline" href={d.change_request_url} rel="noreferrer noopener" target="_blank">Open</a>
                  : <span className="text-muted-foreground">none</span>}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function Diff({ text }: { text: string }) {
  if (!text) return <Hint>No changes yet.</Hint>;
  return (
    <Output label="Changes against the base file" className="max-h-96">
      {text.split("\n").map((l, i) => {
        const add = l.startsWith("+") && !l.startsWith("+++");
        const del = l.startsWith("-") && !l.startsWith("---");
        return (
          <span key={i} className={cn("block", add && "bg-success/10 text-success", del && "bg-destructive/10 text-destructive")}>{l || " "}</span>
        );
      })}
    </Output>
  );
}

export function PipelineEditorPage({ pid, draftId, go }: { pid: string; draftId?: string; go: (to: string) => void }) {
  const qc = useQueryClient();
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
  const d = draft.data;
  const statusState = STATUS[status]?.state ?? "idle";

  return (
    <Page wide>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid, to: `/p/${pid}/runs` }, { label: "Pipeline", to: `/p/${pid}/pipeline` }, { label: "Edit" }]} />
      <PageHeader
        title="Edit pipeline"
        description="Changes are kept as a draft. Nothing reaches git until you propose them, and then only as a change request someone else approves."
        badge={
          <div className="flex flex-wrap items-center gap-2" role="status">
            <Badge variant="outline">{status === "new" ? "Not saved yet" : `Draft ${draftId}`}</Badge>
            {d && <StatusBadge state={statusState}>{STATUS[status]?.label ?? "Closed"}</StatusBadge>}
            {d?.base_sha && <Code>based on {d.base_sha.slice(0, 8)}</Code>}
          </div>
        }
      />
      {loadError && <ErrorAlert title="Could not load the pipeline file">{loadError}</ErrorAlert>}

      {text !== undefined && (
        <>
          <Card className="py-3">
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>Flow</CardTitle>
                <CardDescription>{pipe ? `${pipe.steps.length} steps` : "The flow appears once the file parses."}</CardDescription>
              </div>
              {pipes.length > 1 && (
                <Select value={pipe?.name} onValueChange={(v) => { setPipeName(v); setStepId(undefined); }}>
                  <SelectTrigger aria-label="Pipeline" className="w-48"><SelectValue /></SelectTrigger>
                  <SelectContent>{pipes.map((p) => <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>)}</SelectContent>
                </Select>
              )}
            </CardHeader>
            <CardContent className="px-4">
              {pipe ? <PipelineGraph steps={pipe.steps} current={step?.id} onPick={setStepId} /> : <Hint>The flow appears once the file parses.</Hint>}
            </CardContent>
          </Card>

          <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <div className="grid gap-6">
              <Card>
                <CardHeader><CardTitle>Step inspector</CardTitle></CardHeader>
                <CardContent>
                  {step ? (
                    <div className="grid gap-4">
                      <div className="text-base font-medium">{step.id}</div>
                      <Fields rows={[
                        ["Agent", <Code key="a">{step.agent ?? "none"}</Code>],
                        ["Depends on", step.depends_on.length ? step.depends_on.join(", ") : "nothing"],
                        ["Requires", step.requires.length ? step.requires.join(", ") : "nothing"],
                        ["Produces", step.produces.length ? step.produces.join(", ") : "nothing"],
                        ["Gate", step.gate_role ? `signed by ${step.gate_role}` : "no human gate"],
                      ]} />
                    </div>
                  ) : <Hint>Pick a step in the flow.</Hint>}
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Checks</CardTitle></CardHeader>
                <CardContent className="grid gap-2">
                  {findings.length === 0 ? (
                    <div className="flex items-center justify-between rounded-lg border p-3 text-sm">
                      <span>{stale ? "Checking" : "No problems found"}</span>
                      <StatusBadge state={stale ? "wait" : "ok"}>{stale ? "Checking" : "Valid"}</StatusBadge>
                    </div>
                  ) : findings.map((f, i) => (
                    <div key={i} className="grid gap-1 rounded-lg border p-3 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge state={f.severity === "error" ? "bad" : "wait"}>{f.severity === "error" ? "Error" : "Warning"}</StatusBadge>
                        <span className="font-medium">{f.message}</span>
                      </div>
                      <span className="font-mono text-xs text-muted-foreground">{f.code}{f.path ? ` · ${f.path}` : ""}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>asac.yaml</CardTitle>
                {!editable && <CardDescription>This draft is {status}. Start a new edit to change the file again.</CardDescription>}
              </CardHeader>
              <CardContent>
                <YamlEditor value={text} onChange={setText} badLines={badLines} readOnly={!editable} label="asac.yaml source" />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Changes</CardTitle></CardHeader>
            <CardContent className="grid gap-4">
              <Diff text={dirty || draftId ? (draft.data && !dirty ? draft.data.diff : localDiff(original ?? "", text)) : ""} />
              {conflict && (
                <Alert variant="destructive" role="alert">
                  <AlertTitle>The default branch changed this file since your draft was based on it</AlertTitle>
                  <AlertDescription className="grid gap-3">
                    <p>Copy your edits, start a new edit from the current file and apply them again. Upstream changes:</p>
                    <Diff text={conflict.diff} />
                  </AlertDescription>
                </Alert>
              )}
              {d?.change_request_url && <p className="text-sm">Change request: <a className="underline-offset-4 hover:underline" href={d.change_request_url} rel="noreferrer noopener" target="_blank">{d.change_request_url}</a></p>}
              {(save.error || propose.error) && !conflict && <ErrorAlert title="Could not save">{(save.error ?? propose.error)!.message}</ErrorAlert>}
              <FormActions note={editable ? alone : undefined}>
                <Button variant="outline" disabled={!editable || !dirty || save.isPending} onClick={() => save.mutate()}><Save /> {draftId ? "Save draft" : "Save as draft"}</Button>
                <Button disabled={!draftId || !editable || errors.length > 0 || stale || dirty || propose.isPending} onClick={() => propose.mutate()}><Send /> Propose change</Button>
              </FormActions>
            </CardContent>
          </Card>
        </>
      )}

      <Card className="gap-0 overflow-hidden py-0">
        <CardHeader className="border-b py-4"><CardTitle>Drafts</CardTitle></CardHeader>
        <DraftsList pid={pid} go={go} current={draftId} />
      </Card>
    </Page>
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
