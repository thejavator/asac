import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { Play, Search } from "lucide-react";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Field } from "../components/app/Form";
import { Code, Crumbs, Empty, ErrorAlert, Page, PageHeader, TableCard } from "../components/app/Page";
import { runState } from "@/lib/status";
import { Link } from "../components/Link";
import { StatusBadge } from "../components/StatusBadge";

/** Select needs a non-empty value for "all": map it to "" for the API. */
const ALL = "all";
const STATUSES = [ALL, "running", "gate_waiting", "completed", "failed", "blocked", "killed"];
const STATUS_LABEL: Record<string, string> = { all: "All statuses", gate_waiting: "Waiting for a decision" };

function StartRun({ pid, go, onClose }: { pid: string; go: (to: string) => void; onClose: () => void }) {
  const pipes = useQuery({ queryKey: ["pipelines", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/pipelines", { params: { path: { pid } } })) });
  const [name, setName] = useState("");
  const pipeline = name || pipes.data?.[0]?.name || "";
  const plan = useQuery({
    enabled: !!pipeline,
    queryKey: ["plan", pid, pipeline],
    queryFn: () => unwrap(api.GET("/projects/{pid}/pipelines/{name}/plan", { params: { path: { pid, name: pipeline } } })),
  });
  const start = useMutation({
    mutationFn: () => unwrap(api.POST("/projects/{pid}/runs", { params: { path: { pid } }, body: { pipeline }, headers: csrfHeader() })),
    onSuccess: (r) => go(`/p/${pid}/runs/${r.run_id}`),
  });
  return (
    <Card aria-label="Start a run">
      <CardHeader>
        <CardTitle>Start a run</CardTitle>
        <CardDescription>Check the plan and its token estimate before starting.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <Field id="pipe" label="Pipeline" className="max-w-xs">
          <Select value={pipeline} onValueChange={setName}>
            <SelectTrigger id="pipe" className="w-full"><SelectValue placeholder="Choose a pipeline" /></SelectTrigger>
            <SelectContent>{(pipes.data ?? []).map((p) => <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
        {plan.isPending && pipeline && <Skeleton className="h-24" />}
        {plan.data && (
          <div className="grid gap-3">
            <p className="text-sm">
              <b>{plan.data.steps.length} steps</b>, estimated <b>{plan.data.estimated_tokens.toLocaleString("en")} tokens</b>
              {plan.data.budget_tokens != null && <> of a {plan.data.budget_tokens.toLocaleString("en")} budget</>}.
            </p>
            {plan.data.over_budget && <ErrorAlert title="Over budget">Raise the run budget before starting.</ErrorAlert>}
            <ol aria-label="Plan" className="divide-y rounded-lg border">
              {plan.data.steps.map((s, i) => (
                <li key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                  <span className="w-5 font-mono text-xs text-muted-foreground">{i + 1}</span>
                  <span className="font-medium">{s.id}</span>
                  <span className="font-mono text-xs text-muted-foreground">{s.agent} · {s.mode}</span>
                  {s.gate && <Badge variant="outline">gate {s.gate}</Badge>}
                  <span className="ml-auto font-mono text-xs text-muted-foreground">{s.estimated_tokens.toLocaleString("en")} tok</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {plan.isError && <ErrorAlert title="Could not plan">{plan.error.message}</ErrorAlert>}
        {start.isError && <ErrorAlert title="Could not start the run">{start.error.message}</ErrorAlert>}
      </CardContent>
      <CardFooter className="gap-2">
        <Button disabled={!plan.data || plan.data.over_budget || start.isPending} onClick={() => start.mutate()}><Play /> Start run</Button>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
      </CardFooter>
    </Card>
  );
}

export function RunsPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const [status, setStatus] = useState(ALL);
  const [needle, setNeedle] = useState("");
  const [starting, setStarting] = useState(false);
  const apiStatus = status === ALL ? "" : status;
  const q = useInfiniteQuery({
    queryKey: ["runs", pid, apiStatus, needle],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/projects/{pid}/runs", { params: { path: { pid }, query: { status: apiStatus, q: needle, cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Page>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid, to: `/p/${pid}/runs` }, { label: "Runs" }]} />
      <PageHeader
        title="Runs"
        description="Every run of this project, newest first."
        actions={!starting && <Button onClick={() => setStarting(true)}><Play /> Start a run</Button>}
      />
      {starting && <StartRun pid={pid} go={go} onClose={() => setStarting(false)} />}

      <TableCard
        actions={
          <form role="search" aria-label="Filter runs" className="flex flex-wrap items-center gap-2" onSubmit={(e) => e.preventDefault()}>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger aria-label="Status" className="w-48"><SelectValue /></SelectTrigger>
              <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{STATUS_LABEL[s] ?? runState(s)[1]}</SelectItem>)}</SelectContent>
            </Select>
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input aria-label="Search runs" placeholder="Search runs" className="w-56 pl-8" value={needle} onChange={(e) => setNeedle(e.target.value)} />
            </div>
          </form>
        }
        title="All runs"
      >
        {q.isError && <div className="p-6"><ErrorAlert title="Could not load runs">{q.error.message}</ErrorAlert></div>}
        {q.isPending && <div className="p-6"><Skeleton className="h-40" /></div>}
        {q.data && items.length === 0 && (
          <div className="p-6"><Empty>No run matches. Start one above, with <Code>asac apply</Code>, or from a trigger.</Empty></div>
        )}
        {items.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Run</TableHead><TableHead>Pipeline</TableHead><TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Steps</TableHead><TableHead className="hidden pr-6 md:table-cell">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => {
                const [state, text] = runState(r.status);
                const done = r.steps.filter((s) => s.status === "completed").length;
                return (
                  <TableRow key={r.run_id}>
                    <TableCell className="pl-6 font-mono text-xs">
                      <Link to={`/p/${pid}/runs/${r.run_id}`} go={go} className="font-medium underline-offset-4 hover:underline">{r.run_id}</Link>
                    </TableCell>
                    <TableCell>{r.pipeline}</TableCell>
                    <TableCell><StatusBadge state={state}>{text}</StatusBadge></TableCell>
                    <TableCell className="hidden md:table-cell">
                      <span className="tabular-nums">{done}</span><span className="text-muted-foreground"> of {r.steps.length}</span>
                    </TableCell>
                    <TableCell className="hidden pr-6 font-mono text-xs text-muted-foreground md:table-cell">{r.created_at}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </TableCard>
      {q.hasNextPage && (
        <div><Button variant="outline" disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Load more</Button></div>
      )}
    </Page>
  );
}
