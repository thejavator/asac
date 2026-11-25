import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorAlert, Page, PageHeader, TableCard } from "../components/app/Page";
import { Link } from "../components/Link";
import { StatusBadge } from "../components/StatusBadge";

export function ProjectsPage({ go }: { go: (to: string) => void }) {
  const q = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/projects")) });
  return (
    <Page>
      <PageHeader title="All projects" description="Projects you can see, with what needs attention." />
      {q.isError && <ErrorAlert title="Could not load projects">{q.error.message}</ErrorAlert>}
      {q.isPending && <Skeleton className="h-40" />}
      {q.data && q.data.length === 0 && <Empty>You have no access to any project yet. Ask an organisation admin to add you.</Empty>}
      {q.data && q.data.length > 0 && (
        <TableCard>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Project</TableHead><TableHead>Your roles</TableHead>
                <TableHead className="text-right">Active</TableHead><TableHead className="text-right">Problems</TableHead>
                <TableHead className="pr-6 text-right">Waiting for you</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="pl-6">
                    <div className="flex items-center gap-2">
                      <Link to={`/p/${p.id}/runs`} go={go} className="font-medium underline-offset-4 hover:underline">{p.name}</Link>
                      {p.error && <StatusBadge state="bad">Unavailable</StatusBadge>}
                    </div>
                    {p.team && <div className="text-xs text-muted-foreground">{p.team}</div>}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{p.roles.join(", ") || "reader"}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.active_runs}</TableCell>
                  <TableCell className="text-right">{p.problem_runs > 0 ? <StatusBadge state="bad">{p.problem_runs}</StatusBadge> : <span className="tabular-nums text-muted-foreground">0</span>}</TableCell>
                  <TableCell className="pr-6 text-right">{p.my_pending_gates > 0 ? <StatusBadge state="wait">{p.my_pending_gates}</StatusBadge> : <span className="tabular-nums text-muted-foreground">0</span>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableCard>
      )}
    </Page>
  );
}
