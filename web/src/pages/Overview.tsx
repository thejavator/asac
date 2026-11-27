import { useQuery } from "@tanstack/react-query";
import { Info, ShieldAlert } from "lucide-react";
import { api, unwrap, type Schema } from "../api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Empty, ErrorAlert, Notice, Page, PageHeader, TableCard } from "../components/app/Page";
import { Link } from "../components/Link";
import { StatusBadge } from "../components/StatusBadge";
import { health, passRate, tokens, usd } from "./overviewView";

/** "Declared": every number comes from the runs' own audit, not from a central verifier. */
function Assurance({ level }: { level: Schema["OverviewOut"]["assurance"] }) {
  const verified = level === "verified";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className={verified ? "border-success/25 bg-success/12 text-success" : "text-muted-foreground"}>
          <Info aria-hidden="true" />
          {verified ? "Verified" : "Declared"}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        {verified
          ? "Figures recomputed by the central verifier on each pushed commit."
          : "Figures reported by each project's own runs. A workstation can alter what it reports: these numbers show activity, they do not prove it."}
      </TooltipContent>
    </Tooltip>
  );
}

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <Card className="gap-1 py-4">
      <CardHeader className="px-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">{value}</CardTitle>
      </CardHeader>
      {hint && <CardContent className="px-4 text-xs text-muted-foreground">{hint}</CardContent>}
    </Card>
  );
}

export function OverviewPage({ go }: { go: (to: string) => void }) {
  const q = useQuery({ queryKey: ["overview"], queryFn: () => unwrap(api.GET("/overview")), refetchInterval: 30_000 });
  const data = q.data;
  const t = data?.totals ?? {};
  const security = (t.integrity_violations ?? 0) + (t.sandbox_denials ?? 0);

  return (
    <Page wide>
      <PageHeader
        title="Organisation overview"
        description="Activity, cost and control results across every project you can see."
        badge={data && <Assurance level={data.assurance} />}
      />
      {q.isError && <ErrorAlert title="Could not load the overview">{q.error.message}</ErrorAlert>}
      {q.isPending && <Skeleton className="h-64" />}

      {data && data.assurance === "declared" && (
        <Notice title="These figures are declared">
          They come from what each run reported. Proof that a commit passed its checks needs the central verifier,
          which re-runs them on the pushed code with the protected rules.
        </Notice>
      )}

      {data && (
        <section aria-label="Totals" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Runs" value={t.runs ?? 0} hint={`${t.active ?? 0} active · ${t.problems ?? 0} need attention`} />
          <Stat label="Decisions waiting" value={t.pending_gates ?? 0} />
          <Stat label="Agent cost" value={usd(t.cost_usd ?? 0)} hint={`${tokens(t.tokens ?? 0)} tokens, as reported by the tool`} />
          <Stat
            label="Security events"
            value={
              <span className="flex items-center gap-2">
                {security > 0 && <ShieldAlert className="size-5 text-destructive" aria-hidden="true" />}
                {security}
              </span>
            }
            hint={`${t.integrity_violations ?? 0} rule tampering · ${t.sandbox_denials ?? 0} sandbox refusals`}
          />
        </section>
      )}

      {data && data.projects.length === 0 && (
        <Empty>You have no access to any project yet. Ask an organisation admin to add you.</Empty>
      )}

      {data && data.projects.length > 0 && (
        <TableCard title="By project" description="Worst signal first in each row. Unreadable projects stay listed.">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Project</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Runs</TableHead>
                <TableHead className="text-right">Waiting</TableHead>
                <TableHead className="text-right">Checks passed</TableHead>
                <TableHead className="text-right">Security</TableHead>
                <TableHead className="pr-6 text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.projects.map((p) => {
                const [state, label] = health(p);
                return (
                  <TableRow key={p.project_id}>
                    <TableCell className="pl-6">
                      <Link to={`/p/${p.project_id}/runs`} go={go} className="font-medium underline-offset-4 hover:underline">
                        {p.name}
                      </Link>
                      {p.team && <div className="text-xs text-muted-foreground">{p.team}</div>}
                    </TableCell>
                    <TableCell><StatusBadge state={state}>{label}</StatusBadge></TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.unavailable ? "—" : p.runs}
                      {!p.unavailable && p.problems > 0 && <span className="ml-1 text-destructive">({p.problems} ✕)</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{p.unavailable ? "—" : p.pending_gates}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.unavailable ? "—" : passRate(p.check_pass_rate)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.unavailable ? "—" : p.integrity_violations + p.sandbox_denials}
                    </TableCell>
                    <TableCell className="pr-6 text-right tabular-nums">
                      {p.unavailable ? "—" : usd(p.cost_usd)}
                      {!p.unavailable && p.cost_unknown_runs > 0 && (
                        <div className="text-xs text-muted-foreground">{p.cost_unknown_runs} run(s) without a cost</div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableCard>
      )}
    </Page>
  );
}
