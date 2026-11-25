import { useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Code, Crumbs, ErrorAlert, Fields, Hint, Page, PageHeader } from "../components/app/Page";
import { DefinitionFlow } from "../components/app/StepNode";
import { Link } from "../components/Link";

export function PipelinePage({ pid, go }: { pid: string; go: (to: string) => void }) {
  const q = useQuery({ queryKey: ["pipelines", pid], queryFn: () => unwrap(api.GET("/projects/{pid}/pipelines", { params: { path: { pid } } })) });
  const [name, setName] = useState<string>();
  const [stepId, setStepId] = useState<string>();
  const pipe = q.data?.find((p) => p.name === name) ?? q.data?.[0];
  const step = pipe?.steps.find((s) => s.id === stepId) ?? pipe?.steps[0];
  return (
    <Page>
      <Crumbs go={go} items={[{ label: "All projects", to: "/" }, { label: pid, to: `/p/${pid}/runs` }, { label: "Pipeline" }]} />
      <PageHeader
        title={<>Pipeline {pipe && <Code>{pipe.name}</Code>}</>}
        description="Steps, the evidence each one needs and produces, and who signs each gate."
        actions={
          <>
            {q.data && q.data.length > 1 && (
              <Select value={pipe?.name} onValueChange={(v) => { setName(v); setStepId(undefined); }}>
                <SelectTrigger aria-label="Pipeline" className="w-48"><SelectValue /></SelectTrigger>
                <SelectContent>{q.data.map((p) => <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
            <Button asChild><Link to={`/p/${pid}/pipeline/edit`} go={go}><Pencil /> Edit pipeline</Link></Button>
          </>
        }
      />
      {q.isError && <ErrorAlert title="Could not load pipelines">{q.error.message}</ErrorAlert>}
      {q.isPending && <Skeleton className="h-48" />}
      {pipe && step && (
        <>
          <Card className="py-3">
            <CardContent className="grid gap-3 px-4">
              <DefinitionFlow steps={pipe.steps} current={step.id} onPick={setStepId} />
              <Hint>Each arrow carries the evidence that must exist before the next step may start.</Hint>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{step.id}</CardTitle>
              <CardDescription>Step inspector. Read only: changes are proposed from the editor.</CardDescription>
            </CardHeader>
            <CardContent>
              <Fields
                rows={[
                  ["Agent", <Code key="a">{step.agent ?? "none"}</Code>],
                  ["Depends on", step.depends_on.length ? step.depends_on.join(", ") : "nothing"],
                  ["Requires", step.requires.length ? step.requires.join(", ") : "nothing"],
                  ["Produces", step.produces.length ? step.produces.join(", ") : "nothing"],
                  ["Gate", step.gate_role ? `signed by ${step.gate_role}` : "no human gate"],
                ]}
              />
            </CardContent>
          </Card>
        </>
      )}
    </Page>
  );
}
