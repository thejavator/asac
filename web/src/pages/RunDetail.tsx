import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheckBig, FileDown, GitCommitHorizontal, ShieldAlert, Terminal } from "lucide-react";
import { useMemo, useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { runState, stepState } from "../components/Chip";
import { Link } from "../components/Link";
import { PipelineFlow } from "../components/PipelineFlow";
import { StatusBadge } from "../components/StatusBadge";
import { TriggerLink } from "../components/TriggerLink";

const TABS = ["steps", "output", "deliverables", "hooks", "evidence", "audit"] as const;
type Tab = (typeof TABS)[number];

export function RunDetailPage({ pid, runId, go }: { pid: string; runId: string; go: (to: string) => void }) {
  const q = useQuery({
    queryKey: ["run", pid, runId],
    queryFn: () => unwrap(api.GET("/projects/{pid}/runs/{run_id}", { params: { path: { pid, run_id: runId } } })),
    // a run that is working refreshes by itself; a finished or waiting one does not
    refetchInterval: (query) => (query.state.data?.run.status === "running" ? 2000 : false),
  });
  const qc = useQueryClient();
  const stop = useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{pid}/runs/{run_id}/stop", { params: { path: { pid, run_id: runId } }, headers: csrfHeader() })),
    onSuccess: () => qc.invalidateQueries(),
  });
  const [tab, setTab] = useState<Tab>("steps");
  const [picked, setPicked] = useState<string>();

  const data = q.data;
  const outputs = useMemo(() => data?.audit.filter((a) => a.action === "runner.output") ?? [], [data]);
  const hooks = useMemo(() => data?.audit.filter((a) => a.action === "hook.passed" || a.action === "hook.failed") ?? [], [data]);

  if (q.isError) {
    return (
      <Alert variant="destructive" role="alert">
        <ShieldAlert />
        <AlertTitle>Could not load this run</AlertTitle>
        <AlertDescription>{q.error.message}</AlertDescription>
      </Alert>
    );
  }
  if (!data) return <RunSkeleton />;

  const { run, evidence, gates, audit, artifacts, spend } = data;
  const [runTone, runText] = runState(run.status);
  const done = run.steps.filter((s) => s.status === "completed").length;
  const approved = gates.filter((g) => g.status === "approved").length;
  const pending = gates.filter((g) => g.status === "pending").length;
  const current = picked ?? run.steps.find((s) => s.status !== "completed" && s.status !== "pending")?.id ?? run.steps[0]?.id;
  const currentStep = run.steps.find((s) => s.id === current);
  const failedHooks = hooks.filter((h) => h.action === "hook.failed");
  const live = run.status === "running" || run.status === "gate_waiting";
  const problem = run.status === "failed" || run.status === "blocked";

  const label: Record<Tab, string> = { steps: "Steps", output: "Output", deliverables: "Deliverables", hooks: "Hooks", evidence: "Evidence", audit: "Audit" };
  const count: Record<Tab, number | undefined> = {
    steps: undefined, output: outputs.length || undefined, deliverables: artifacts.length || undefined,
    hooks: hooks.length || undefined, evidence: evidence.length, audit: audit.length,
  };

  return (
    <div className="mx-auto grid w-full max-w-6xl grid-cols-[minmax(0,1fr)] gap-6">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem><BreadcrumbLink asChild><Link to="/" go={go}>All projects</Link></BreadcrumbLink></BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem><BreadcrumbLink asChild><Link to={`/p/${pid}/runs`} go={go}>{pid}</Link></BreadcrumbLink></BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem><BreadcrumbPage className="font-mono text-sm">{run.run_id}</BreadcrumbPage></BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Title and actions */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 id="run-h" className="text-3xl font-semibold tracking-tight">{run.pipeline}</h1>
            <StatusBadge state={runTone}>{runText}</StatusBadge>
          </div>
          <p className="text-sm text-muted-foreground">
            {done} of {run.steps.length} steps done
            {pending > 0 && <> · <span className="font-medium text-foreground">{pending} decision{pending > 1 ? "s" : ""} waiting</span></>}
            {run.status === "running" && <> · <span role="status">live, refreshing every 2 seconds</span></>}
          </p>
          <dl className="flex flex-wrap gap-2 text-sm">
            <Fact k="Run"><span className="font-mono">{run.run_id}</span></Fact>
            <Fact k="Pipeline">{run.pipeline}</Fact>
            {data.trigger && <Fact k="Trigger"><TriggerLink trigger={data.trigger} /></Fact>}
            <Fact k="Created"><span className="font-mono">{run.created_at}</span></Fact>
          </dl>
        </div>

        {live && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={stop.isPending}>Stop run</Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Stop this run?</AlertDialogTitle>
                <AlertDialogDescription>It cannot be resumed. The stop is written to the audit trail.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep running</AlertDialogCancel>
                <AlertDialogAction onClick={() => stop.mutate()}>Stop run</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </header>

      {stop.isError && (
        <Alert variant="destructive" role="alert">
          <AlertTitle>Could not stop the run</AlertTitle>
          <AlertDescription>{stop.error.message}</AlertDescription>
        </Alert>
      )}

      {problem && failedHooks.length > 0 && (
        <Alert variant="destructive" role="alert">
          <ShieldAlert />
          <AlertTitle>{failedHooks.length === 1 ? "A hook blocked this run" : `${failedHooks.length} hooks failed`}</AlertTitle>
          <AlertDescription>
            <span>
              <span className="font-mono">{hookMoment(failedHooks[0]!.detail.split("\n")[0]!).name}</span>{" "}
              failed at <b>{failedHooks[0]!.step_id}</b>. Open the Hooks tab for its output.
            </span>
          </AlertDescription>
        </Alert>
      )}

      {/* Metrics: one slim strip, secondary to the tabs below */}
      <Card className="py-0">
        <dl aria-label="Run metrics" className="grid grid-cols-2 divide-x divide-y sm:grid-cols-4 sm:divide-y-0">
          <Metric title="Steps done" value={`${done}/${run.steps.length}`}>
            <Progress value={run.steps.length ? (done / run.steps.length) * 100 : 0} aria-label="Steps done" className="h-1" />
          </Metric>
          <Metric title="Decisions" value={String(approved)} note={pending ? `${pending} waiting` : "approved"} />
          <Metric title="Evidence" value={String(evidence.length)} note={`${evidence.filter((e) => e.approved_by).length} approved`} />
          <Metric title="Spend" value={`$${spend.cost_usd.toFixed(2)}`} note={`${spend.tokens.toLocaleString("en")} tokens`} />
        </dl>
      </Card>

      {/* Pipeline */}
      <Card className="py-3">
        <CardContent className="px-4">
          <PipelineFlow steps={run.steps} current={current} onPick={(id) => { setPicked(id); setTab("steps"); }} />
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="gap-4">
        <TabsList aria-label="Run sections" className="h-auto min-h-11 w-full flex-wrap justify-start sm:w-fit">
          {TABS.map((t) => (
            <TabsTrigger key={t} value={t} className="flex-none gap-2 px-3 text-sm sm:px-4">
              {label[t]}
              {count[t] !== undefined && (
                <Badge variant="secondary" className={t === "hooks" && failedHooks.length ? "bg-destructive/10 text-destructive" : ""}>{count[t]}</Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* STEPS */}
        <TabsContent value="steps" className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <Card className="gap-0 py-0">
            <ol aria-label="Steps" className="divide-y">
              {run.steps.map((s) => {
                const [state, text] = stepState(s.status);
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => setPicked(s.id)}
                      aria-current={s.id === current ? "step" : undefined}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none aria-[current=step]:bg-accent"
                    >
                      <StatusBadge state={state} className="shrink-0">{text}</StatusBadge>
                      <span className="min-w-0 truncate text-sm font-medium">{s.id}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-xl">
                {current}
                {currentStep && <StatusBadge state={stepState(currentStep.status)[0]}>{stepState(currentStep.status)[1]}</StatusBadge>}
              </CardTitle>
              <CardDescription>
                {hooks.filter((h) => h.step_id === current).length} hook result(s) · {outputs.filter((o) => o.step_id === current).length} runner output(s) ·{" "}
                {artifacts.filter((a) => a.step_id === current).length} file(s)
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-6">
              {gates.filter((g) => g.step_id === current).map((g) => (
                <div key={g.gate_id} className="flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm">
                  <CircleCheckBig className="size-4 text-muted-foreground" />
                  <span>Gate <span className="font-mono">{g.gate_id}</span> · {g.role ?? "any role"}</span>
                  <StatusBadge state={g.status === "pending" ? "wait" : g.status === "approved" ? "ok" : "bad"}>{g.status}</StatusBadge>
                  {g.comment && <span className="text-muted-foreground">“{g.comment}”</span>}
                  {g.status === "pending" && g.can_decide && (
                    <Button asChild size="sm" className="ml-auto"><Link to={`/p/${pid}/decisions`} go={go}>Decide in Decision Room</Link></Button>
                  )}
                </div>
              ))}

              <StepSection title="Hooks" icon={<ShieldAlert className="size-4" />} empty="No hook has run for this step.">
                {hooks.filter((h) => h.step_id === current).map((h) => <HookRow key={h.seq} h={h} />)}
              </StepSection>

              <StepSection title="Runner output" icon={<Terminal className="size-4" />} empty="No runner output for this step.">
                {outputs.filter((o) => o.step_id === current).map((o) => <OutputBlock key={o.seq} detail={o.detail} />)}
              </StepSection>

              <StepSection title="Files" icon={<FileDown className="size-4" />} empty="No file was stored by this step.">
                {artifacts.filter((a) => a.step_id === current).map((a) => (
                  <ArtifactRow key={a.name} a={a} href={artifactHref(pid, run.run_id, a.name)} />
                ))}
              </StepSection>
            </CardContent>
          </Card>
        </TabsContent>

        {/* OUTPUT */}
        <TabsContent value="output">
          <Card>
            <CardHeader><CardTitle>Runner output</CardTitle><CardDescription>What each step printed while it ran.</CardDescription></CardHeader>
            <CardContent className="grid gap-4">
              {outputs.length === 0 ? <Empty>No step has run in a runner yet.</Empty> : outputs.map((o) => (
                <div key={o.seq} className="grid gap-2">
                  <p className="text-sm"><b>{o.step_id}</b> <span className="font-mono text-muted-foreground">{o.detail.split("\n")[0]}</span></p>
                  <OutputBlock detail={o.detail} />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* DELIVERABLES */}
        <TabsContent value="deliverables">
          <Card className="gap-0 overflow-hidden pb-0">
            <CardHeader className="pb-4"><CardTitle>Deliverables</CardTitle><CardDescription>Files stored by this run.</CardDescription></CardHeader>
            {artifacts.length === 0 ? <CardContent className="pb-6"><Empty>No files were stored for this run.</Empty></CardContent> : (
              <Table>
                <TableHeader>
                  <TableRow><TableHead className="pl-6">File</TableHead><TableHead>Step</TableHead><TableHead>Size</TableHead><TableHead className="hidden md:table-cell">SHA-256</TableHead></TableRow>
                </TableHeader>
                <TableBody>
                  {artifacts.map((a) => (
                    <TableRow key={a.name}>
                      <TableCell className="pl-6"><a className="font-medium underline-offset-4 hover:underline" href={artifactHref(pid, run.run_id, a.name)} download>{a.name}</a></TableCell>
                      <TableCell>{a.step_id}</TableCell>
                      <TableCell className="font-mono">{a.size.toLocaleString("en")} B</TableCell>
                      <TableCell className="hidden font-mono text-muted-foreground md:table-cell">{a.sha256.slice(0, 16)}…</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        </TabsContent>

        {/* HOOKS */}
        <TabsContent value="hooks">
          <Card>
            <CardHeader><CardTitle>Hook results</CardTitle><CardDescription>Checks that ran before or after a step.</CardDescription></CardHeader>
            <CardContent className="grid gap-3">
              {hooks.length === 0 ? <Empty>No hook has run for this run.</Empty> : hooks.map((h) => <HookRow key={h.seq} h={h} showStep />)}
            </CardContent>
          </Card>
        </TabsContent>

        {/* EVIDENCE */}
        <TabsContent value="evidence">
          <Card>
            <CardHeader><CardTitle>Evidence chain</CardTitle><CardDescription>What each step produced, and who approved it.</CardDescription></CardHeader>
            <CardContent>
              {evidence.length === 0 ? <Empty>No evidence yet.</Empty> : (
                <ol className="relative grid gap-5 border-l pl-6">
                  {evidence.map((e) => (
                    <li key={e.evidence_id} className="relative">
                      <span
                        aria-hidden="true"
                        className={`absolute top-1 -left-[1.9rem] size-3 rounded-full border-2 bg-background ${e.bootstrapped ? "border-dashed border-muted-foreground" : e.approved_by ? "border-success" : "border-foreground"}`}
                      />
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-medium">{e.evidence_id}</span>
                        <Badge variant="outline">{e.bootstrapped ? "bootstrapped" : e.approved_by ? "approved by a person" : "produced by a step"}</Badge>
                      </div>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {e.bootstrapped ? "Bootstrapped" : <>Produced by <b className="text-foreground">{e.produced_by}</b></>}
                        {e.approved_by && <> · approved by <b className="text-foreground">{e.approved_by}</b></>}
                        {" · "}<span className="font-mono">{e.at}</span>
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* AUDIT */}
        <TabsContent value="audit">
          <Card className="gap-0 overflow-hidden pb-0">
            <CardHeader className="pb-4"><CardTitle>Audit trail</CardTitle><CardDescription>Every action on this run, in order.</CardDescription></CardHeader>
            <Table>
              <TableHeader>
                <TableRow><TableHead className="hidden pl-6 md:table-cell">When</TableHead><TableHead>Who</TableHead><TableHead>Action</TableHead><TableHead>Detail</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {audit.map((a) => (
                  <TableRow key={a.seq}>
                    <TableCell className="hidden pl-6 font-mono text-muted-foreground md:table-cell">{a.at}</TableCell>
                    <TableCell>{a.actor}</TableCell>
                    <TableCell className="font-mono">{a.action}</TableCell>
                    <TableCell className="max-w-md whitespace-normal break-words">
                      {a.detail.length > 120 ? (
                        <Tooltip>
                          <TooltipTrigger asChild><span className="cursor-default">{a.detail.slice(0, 120)}…</span></TooltipTrigger>
                          <TooltipContent className="max-w-sm whitespace-pre-wrap break-words">{a.detail}</TooltipContent>
                        </Tooltip>
                      ) : a.detail}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

const artifactHref = (pid: string, runId: string, name: string) =>
  `/api/v1/projects/${encodeURIComponent(pid)}/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`;

function Fact({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-md border bg-card px-2.5 py-1">
      <dt className="text-xs text-muted-foreground">{k}</dt>
      <dd className="m-0">{children}</dd>
    </div>
  );
}

function Metric({ title, value, note, children }: { title: string; value: string; note?: string; children?: React.ReactNode }) {
  return (
    <div className="grid gap-1 px-4 py-3">
      <dt className="text-xs text-muted-foreground">{title}</dt>
      <dd className="m-0 flex items-baseline gap-2">
        <span className="text-xl font-semibold tracking-tight">{value}</span>
        {note && <span className="truncate text-xs text-muted-foreground">{note}</span>}
      </dd>
      {children}
    </div>
  );
}

function StepSection({ title, icon, empty, children }: { title: string; icon: React.ReactNode; empty: string; children: React.ReactNode[] }) {
  const has = children.length > 0;
  return (
    <section className="grid gap-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">{icon}{title}</h3>
      {has ? <div className="grid gap-3">{children}</div> : <p className="text-sm text-muted-foreground">{empty}</p>}
    </section>
  );
}

function HookRow({ h, showStep }: { h: { seq: number; action: string; step_id?: string | null; detail: string }; showStep?: boolean }) {
  const [head, ...rest] = h.detail.split("\n");
  const { name, moment } = hookMoment(head!);
  const ok = h.action === "hook.passed";
  return (
    <div className="grid gap-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <StatusBadge state={ok ? "ok" : "bad"}>{ok ? "Passed" : "Failed"}</StatusBadge>
        <span className="font-mono font-medium">{name}</span>
        <span className="text-muted-foreground">{moment}{showStep && <> <b className="text-foreground">{h.step_id}</b></>}</span>
      </div>
      {rest.length > 0 && <OutputBlock detail={h.detail} />}
    </div>
  );
}

/** The first line of a runner/hook detail is a header; the rest is the output. */
function OutputBlock({ detail }: { detail: string }) {
  const text = detail.split("\n").slice(1).join("\n");
  if (!text.trim()) return null;
  return (
    <pre tabIndex={0} className="max-h-72 overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none">
      {text}
    </pre>
  );
}

function ArtifactRow({ a, href }: { a: { name: string; size: number; sha256: string }; href: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
      <GitCommitHorizontal className="size-4 text-muted-foreground" />
      <a className="font-mono font-medium underline-offset-4 hover:underline" href={href} download>{a.name}</a>
      <span className="font-mono text-xs text-muted-foreground">{a.size.toLocaleString("en")} B</span>
      <span className="ml-auto font-mono text-xs text-muted-foreground">sha256:{a.sha256.slice(0, 12)}</span>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{children}</p>;
}

function RunSkeleton() {
  return (
    <div className="mx-auto grid w-full max-w-6xl grid-cols-[minmax(0,1fr)] gap-6" aria-busy="true">
      <Skeleton className="h-4 w-64" />
      <Skeleton className="h-10 w-96" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
      <Skeleton className="h-32" />
      <Skeleton className="h-64" />
    </div>
  );
}

/** "pre_tool no-secrets" -> before the agent of the step; "post_step x" -> after the step.
 *  Audits written before the moment was recorded have only the name: say "during". */
export function hookMoment(head: string): { name: string; moment: string } {
  const [first, ...more] = head.split(" ");
  if (more.length > 0 && first === "pre_tool") return { name: more.join(" "), moment: "before the agent of step" };
  if (more.length > 0 && first === "post_step") return { name: more.join(" "), moment: "after step" };
  return { name: head, moment: "during step" };
}
