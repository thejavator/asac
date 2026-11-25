import { useInfiniteQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api, unwrap } from "../api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Crumbs, Empty, ErrorAlert, Page, PageHeader, TableCard } from "../components/app/Page";
import { Link } from "../components/Link";
import { cn } from "@/lib/utils";

export function AuditPage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const q = useInfiniteQuery({
    queryKey: ["audit", pid],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/projects/{pid}/audit", { params: { path: { pid }, query: { cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Page>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid, to: `/p/${pid}/runs` }, { label: "Audit trail" }]} />
      <PageHeader
        title="Audit trail"
        description="Every decision, change and denial, newest first. Entries cannot be edited."
        actions={<Button variant="outline" asChild><a href={`/api/v1/projects/${encodeURIComponent(pid)}/audit.csv`} download><Download /> Export CSV</a></Button>}
      />
      {q.isError && <ErrorAlert title="Could not load the audit trail">{q.error.message}</ErrorAlert>}
      {q.isPending && <Skeleton className="h-64" />}
      {q.data && items.length === 0 && <Empty>Nothing recorded yet.</Empty>}
      {items.length > 0 && (
        <TableCard>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="hidden pl-6 md:table-cell">When</TableHead><TableHead>Who</TableHead><TableHead>Action</TableHead>
                <TableHead className="hidden md:table-cell">Run</TableHead><TableHead className="pr-6">Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((a) => (
                <TableRow key={a.seq} className={cn(a.action === "gate.denied" && "bg-destructive/5 hover:bg-destructive/10")}>
                  <TableCell className="hidden pl-6 font-mono text-xs text-muted-foreground md:table-cell">{a.at}</TableCell>
                  <TableCell>{a.actor}</TableCell>
                  <TableCell className={cn("font-mono text-xs", a.action === "gate.denied" && "text-destructive")}>{a.action}</TableCell>
                  <TableCell className="hidden font-mono text-xs md:table-cell">
                    {a.run_id ? <Link to={`/p/${pid}/runs/${a.run_id}`} go={go} className="underline-offset-4 hover:underline">{a.run_id}</Link> : ""}
                  </TableCell>
                  <TableCell className="max-w-md pr-6 whitespace-normal break-words">{a.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableCard>
      )}
      {q.hasNextPage && (
        <div><Button variant="outline" disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Load more</Button></div>
      )}
    </Page>
  );
}
