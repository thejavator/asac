import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Inbox, X } from "lucide-react";
import { useState } from "react";
import { api, csrfHeader, unwrap } from "../api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Crumbs, Empty, ErrorAlert, Fields, Hint, Output, Page, PageHeader } from "../components/app/Page";
import { Field, FormActions } from "../components/app/Form";
import { PipelineFlow } from "../components/PipelineFlow";
import { Link } from "../components/Link";
import { StatusBadge } from "../components/StatusBadge";
import { TriggerLink } from "../components/TriggerLink";
import { dueText, money, signatureNote } from "./decisionView";

export function DecisionRoom({ pid, me, go }: { pid?: string; me: string; go: (to: string) => void }) {
  const [onlyMine, setOnlyMine] = useState(false);
  const qc = useQueryClient();
  const gates = useQuery({
    queryKey: ["decisions", pid ?? "all", onlyMine],
    queryFn: () => unwrap(api.GET("/decisions", { params: { query: { project: pid, mine: onlyMine } } })),
  });
  const [picked, setPicked] = useState<string>();
  const [comment, setComment] = useState("");
  const list = gates.data ?? [];
  const gate = list.find((g) => g.gate_id === picked) ?? list[0];
  const gpid = gate?.project_id ?? "";
  const run = useQuery({
    enabled: !!gate,
    queryKey: ["run", gpid, gate?.run_id],
    queryFn: () => unwrap(api.GET("/projects/{pid}/runs/{run_id}", { params: { path: { pid: gpid, run_id: gate!.run_id } } })),
  });
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      unwrap(api.POST("/projects/{pid}/gates/{gate_id}/decision", {
        params: { path: { pid: gpid, gate_id: gate!.gate_id } },
        body: { decision, comment },
        headers: csrfHeader(),
      })),
    onSuccess: () => {
      setComment("");
      void qc.invalidateQueries();
    },
  });

  return (
    <Page wide>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid ?? "All projects", to: pid ? `/p/${pid}/runs` : undefined }, { label: "Decision Room" }]} />
      <PageHeader
        title="Decision Room"
        description={`Decisions that wait for a person${pid ? " in this project" : ", in every project you can see"}. Each one shows what was built, what was checked and who signed before you.`}
        actions={
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={onlyMine} onCheckedChange={(v) => setOnlyMine(v === true)} />
            Only what I can sign
          </label>
        }
      />
      {gates.isError && <ErrorAlert title="Could not load decisions">{gates.error.message}</ErrorAlert>}
      {gates.isPending && <Skeleton className="h-96" />}
      {gates.data && list.length === 0 && <Empty>Nothing is waiting for a decision.</Empty>}

      {gate && (
        <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          {/* Queue */}
          <Card className="gap-0 py-0 lg:sticky lg:top-4">
            <CardHeader className="border-b py-4">
              <CardTitle className="flex items-center justify-between">
                Waiting <Badge variant="secondary">{list.length}</Badge>
              </CardTitle>
            </CardHeader>
            <ScrollArea className="max-h-[70vh]">
              <ol className="divide-y">
                {list.map((g) => {
                  const active = g.gate_id === gate.gate_id;
                  const due = dueText(g.seconds_left);
                  const late = g.seconds_left != null && g.seconds_left < 0;
                  return (
                    <li key={g.gate_id}>
                      <a
                        href={`#${g.gate_id}`}
                        aria-current={active ? "true" : undefined}
                        onClick={(e) => { e.preventDefault(); setPicked(g.gate_id); }}
                        className={cn(
                          "grid gap-1 px-4 py-3 text-sm transition-colors hover:bg-accent",
                          active && "bg-accent",
                          late && "border-l-2 border-l-destructive",
                        )}
                      >
                        <span className="font-medium">Approve {g.step_id}</span>
                        <span className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
                          {!pid && <span>{g.project_name}</span>}
                          <span className="font-mono">{g.run_id}</span>
                          {g.pipeline && <span>{g.pipeline}</span>}
                        </span>
                        {due && <span className={cn("text-xs", late ? "text-destructive" : "text-muted-foreground")}>{due}</span>}
                      </a>
                    </li>
                  );
                })}
              </ol>
            </ScrollArea>
          </Card>

          {/* Decision */}
          <div className="grid min-w-0 gap-6">
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge state="wait">Waiting for {gate.role ?? "any role"}</StatusBadge>
                </div>
                <CardTitle className="text-xl">Approve {gate.step_id}</CardTitle>
              </CardHeader>
              <CardContent>
                <Fields
                  rows={[
                    ...(!pid ? [["Project", gate.project_name] as [string, React.ReactNode]] : []),
                    ["Run", <Link key="r" to={`/p/${gate.project_id}/runs/${gate.run_id}`} go={go} className="font-mono text-xs underline-offset-4 hover:underline">{gate.run_id}</Link>],
                    ...(gate.pipeline ? [["Pipeline", gate.pipeline] as [string, React.ReactNode]] : []),
                    ...(run.data?.trigger ? [["Trigger", <TriggerLink key="t" trigger={run.data.trigger} />] as [string, React.ReactNode]] : []),
                    ...(gate.run_started_at ? [["Started", <span key="s" className="font-mono text-xs">{gate.run_started_at}</span>] as [string, React.ReactNode]] : []),
                    ["Requested", <span key="q" className="font-mono text-xs">{gate.requested_at}</span>],
                    ...(gate.timeout_at ? [["Due", <span key="d" className="font-mono text-xs">{gate.timeout_at}{dueText(gate.seconds_left) && ` (${dueText(gate.seconds_left)})`}</span>] as [string, React.ReactNode]] : []),
                    ["Cost so far", money(gate.cost_usd)],
                    ...(gate.subject ? [["Commit", <span key="c" className="font-mono text-xs" title={gate.subject}>{gate.subject.slice(0, 12)}</span>] as [string, React.ReactNode]] : []),
                  ]}
                />
              </CardContent>
            </Card>

            {gate.checks.length > 0 && (
              <Card>
                <CardHeader><CardTitle>Checks made before this decision</CardTitle></CardHeader>
                <CardContent className="grid gap-3">
                  {gate.checks.map((c, i) => (
                    <div key={i} className="grid gap-2 rounded-lg border p-3">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <StatusBadge state={c.passed ? "ok" : "bad"}>{c.passed ? "Passed" : "Failed"}</StatusBadge>
                        <span className="font-mono font-medium">{c.name}</span>
                        <span className="text-muted-foreground">{c.moment === "pre_tool" ? "Hook, before the agent" : c.moment === "post_step" ? "Hook, after the step" : "Hook"}</span>
                      </div>
                      {c.output && <Output>{c.output}</Output>}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {gate.files.length > 0 && (
              <Card>
                <CardHeader><CardTitle>What this step changed</CardTitle></CardHeader>
                <CardContent className="grid gap-2">
                  {gate.files.filter((f) => !f.mounted).map((f) => (
                    <div key={f.path} className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                      <Badge variant={f.change === "deleted" ? "destructive" : "secondary"} className="w-6 justify-center font-mono">
                        {f.change === "added" ? "+" : f.change === "deleted" ? "−" : "~"}
                      </Badge>
                      <span className="font-mono text-xs break-all">{f.path}</span>
                      <span className="ml-auto text-xs text-muted-foreground">{f.change} in commit {gate.subject?.slice(0, 12)}</span>
                    </div>
                  ))}
                  {gate.files.some((f) => f.mounted) && (
                    <Hint>
                      Also in this commit, set up by ASAC for the tool, not written by the agent:{" "}
                      {gate.files.filter((f) => f.mounted).map((f, i) => (
                        <span key={f.path}>{i > 0 && ", "}<span className="font-mono text-xs">{f.path}</span></span>
                      ))}
                    </Hint>
                  )}
                </CardContent>
              </Card>
            )}

            {run.data && (
              <Card>
                <CardHeader><CardTitle>Where this run stands</CardTitle></CardHeader>
                <CardContent className="grid grid-cols-[minmax(0,1fr)] gap-6">
                  <PipelineFlow steps={run.data.run.steps} current={gate.step_id} onPick={() => {}} />
                  <div className="grid gap-3">
                    <h3 className="text-sm font-medium">Evidence chain</h3>
                    <ol className="relative grid gap-4 border-l pl-6">
                      {run.data.evidence.map((e) => (
                        <li key={e.evidence_id} className="relative">
                          <span aria-hidden="true" className={cn("absolute top-1 -left-[1.9rem] size-3 rounded-full border-2 bg-background", e.bootstrapped ? "border-dashed border-muted-foreground" : "border-success")} />
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <span className="font-mono font-medium">{e.evidence_id}</span>
                            <Badge variant="outline">{e.bootstrapped ? "bootstrapped" : "produced by agent"}</Badge>
                          </div>
                          <p className="mt-1 text-sm text-muted-foreground">
                            {e.bootstrapped ? signatureNote(e) : `${e.produced_by}${signatureNote(e) ? ` · ${signatureNote(e)}` : ""}`}
                            {" · "}<span className="font-mono text-xs">{e.at}</span>
                          </p>
                        </li>
                      ))}
                      <li className="relative">
                        <span aria-hidden="true" className="absolute top-1 -left-[1.9rem] size-3 rounded-full border-2 border-dashed border-warning bg-background" />
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-mono font-medium">{gate.step_id}</span>
                          <Badge variant="outline">waiting for {gate.role ?? "any role"}</Badge>
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">Your signature produces this evidence.</p>
                      </li>
                    </ol>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle>Your decision</CardTitle>
                <CardDescription>Signed with your name and kept in the audit trail.</CardDescription>
              </CardHeader>
              <CardContent>
                {gate.can_decide ? (
                  <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); decide.mutate("approve"); }}>
                    <Field id="comment" label="Comment" hint="Required if you reject.">
                      <Textarea id="comment" name="comment" maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
                    </Field>
                    {decide.isError && <ErrorAlert title="Could not record the decision">{decide.error.message}</ErrorAlert>}
                    <FormActions note={`Signed as ${me}`}>
                      <Button type="submit" disabled={decide.isPending}><Check /> Approve</Button>
                      <Button type="button" variant="destructive" disabled={decide.isPending || !comment.trim()} onClick={() => decide.mutate("reject")}><X /> Reject</Button>
                    </FormActions>
                  </form>
                ) : (
                  <Alert>
                    <Inbox />
                    <AlertTitle>You can read this decision, not sign it</AlertTitle>
                    <AlertDescription>It needs the role <b>{gate.role}</b>.</AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </Page>
  );
}
