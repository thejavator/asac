import { useQueries, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Crumbs, Empty, ErrorAlert, Page, PageHeader, TableCard } from "../components/app/Page";
import { runState } from "@/lib/status";
import { Link } from "../components/Link";
import { StatusBadge } from "../components/StatusBadge";

const PROBLEMS = ["failed", "blocked", "killed"];

export function ErrorsPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const qs = useQueries({
    queries: PROBLEMS.map((status) => ({
      queryKey: ["runs", pid, status, ""],
      queryFn: () => unwrap(api.GET("/projects/{pid}/runs", { params: { path: { pid }, query: { status, limit: 100 } } })),
    })),
  });
  const failed = qs.find((q) => q.isError);
  const items = qs.flatMap((q) => q.data?.items ?? []).sort((a, b) => b.created_at.localeCompare(a.created_at));
  const ev = useQuery({
    queryKey: ["audit-problems", pid],
    queryFn: () => unwrap(api.GET("/projects/{pid}/audit", { params: { path: { pid }, query: { problems: true, limit: 50 } } })),
  });
  const events = ev.data?.items ?? [];
  const loading = qs.some((q) => q.isLoading);
  return (
    <Page>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid, to: `/p/${pid}/runs` }, { label: "Errors" }]} />
      <PageHeader title="Errors" description="Runs that failed, were blocked by a policy or hook, or were stopped. Open one to see where it stopped." />
      {failed?.error && <ErrorAlert title="Could not load errors">{failed.error.message}</ErrorAlert>}
      {loading && <Skeleton className="h-40" />}
      {!loading && !failed && items.length === 0 && <Empty>No run needs attention.</Empty>}
      {items.length > 0 && (
        <TableCard title="Runs" description={items.length === 1 ? "1 run needs attention." : `${items.length} runs need attention.`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Run</TableHead><TableHead>Pipeline</TableHead><TableHead>Status</TableHead>
                <TableHead>Stopped at</TableHead><TableHead className="hidden pr-6 md:table-cell">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => {
                const at = r.steps.find((s) => s.status === "failed" || s.status === "blocked" || s.status === "killed");
                const [state, text] = runState(r.status);
                return (
                  <TableRow key={r.run_id}>
                    <TableCell className="pl-6 font-mono text-xs">
                      <Link to={`/p/${pid}/runs/${r.run_id}`} go={go} className="font-medium underline-offset-4 hover:underline">{r.run_id}</Link>
                    </TableCell>
                    <TableCell>{r.pipeline}</TableCell>
                    <TableCell><StatusBadge state={state}>{text}</StatusBadge></TableCell>
                    <TableCell className="font-mono text-xs">{at?.id ?? "n/a"}</TableCell>
                    <TableCell className="hidden pr-6 font-mono text-xs text-muted-foreground md:table-cell">{r.created_at}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableCard>
      )}

      {ev.isError && <ErrorAlert title="Could not load events">{ev.error.message}</ErrorAlert>}
      {ev.data && (
        <TableCard
          title="Events"
          description="Denied approvals, failed or blocked steps, hook failures, expired gates, escalations and stopped runs, newest first."
        >
          {events.length === 0 ? <div className="p-6"><Empty>No event needs attention.</Empty></div> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="hidden pl-6 md:table-cell">When</TableHead><TableHead>Event</TableHead>
                  <TableHead>Run</TableHead><TableHead>Step</TableHead><TableHead className="pr-6">Detail</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((a) => (
                  <TableRow key={a.seq}>
                    <TableCell className="hidden pl-6 font-mono text-xs text-muted-foreground md:table-cell">{a.at}</TableCell>
                    <TableCell className="font-mono text-xs text-destructive">{a.action}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {a.run_id ? <Link to={`/p/${pid}/runs/${a.run_id}`} go={go} className="underline-offset-4 hover:underline">{a.run_id}</Link> : ""}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{a.step_id ?? ""}</TableCell>
                    <TableCell className="max-w-md pr-6 whitespace-normal break-words">{a.detail}</TableCell>
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
