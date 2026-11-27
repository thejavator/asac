import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, setCsrf, unwrap, Unauthenticated } from "./api/client";
import { AppShell } from "./components/AppShell";
import { PageErrorBoundary } from "./components/app/ErrorBoundary";
import { ErrorAlert } from "./components/app/Page";
import { Skeleton } from "@/components/ui/skeleton";
import { AccessPage } from "./pages/Access";
import { AdminPage } from "./pages/Admin";
import { AuditPage } from "./pages/Audit";
import { ErrorsPage } from "./pages/Errors";
import { PipelinePage } from "./pages/Pipeline";
import { PipelineEditorPage } from "./pages/PipelineEditor";
import { VariablesPage } from "./pages/Variables";
import { DecisionRoom } from "./pages/DecisionRoom";
import { ProjectsPage } from "./pages/Projects";
import { RunDetailPage } from "./pages/RunDetail";
import { RunsPage } from "./pages/Runs";
import { LoginPage } from "./pages/Login";
import { OverviewPage } from "./pages/Overview";
import { useRoute } from "./route";

export function App() {
  const [parts, go] = useRoute();
  const me = useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/me")) });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/projects")), refetchInterval: 30_000 });
  useEffect(() => {
    if (me.data) setCsrf(me.data.csrf);
  }, [me.data]);

  const waiting = (projects.data ?? []).reduce((n, p) => n + p.my_pending_gates, 0);
  useEffect(() => {
    document.title = waiting > 0 ? `(${waiting}) ASAC` : "ASAC governance";
  }, [waiting]);

  if (me.error instanceof Unauthenticated) return <LoginPage />;
  if (me.isError) return <ErrorAlert title="Could not load your session">{me.error.message}</ErrorAlert>;
  if (!me.data) return <Skeleton className="m-6 h-40" />;

  const [first, pid, section, id, draftId] = parts;
  const project = first === "p" ? projects.data?.find((p) => p.id === pid) : undefined;
  const mine = project?.my_pending_gates ?? 0;
  const allMine = (projects.data ?? []).reduce((n, p) => n + p.my_pending_gates, 0);
  const here = section ?? "runs";

  let page: React.ReactNode;
  if (first === "p" && pid && section === "decisions") page = <DecisionRoom pid={pid} me={me.data.name} go={go} />;
  else if (first === "p" && pid && section === "errors") page = <ErrorsPage pid={pid} go={go} />;
  else if (first === "p" && pid && section === "pipeline" && id === "edit") page = <PipelineEditorPage pid={pid} draftId={draftId} go={go} />;
  else if (first === "p" && pid && section === "pipeline") page = <PipelinePage pid={pid} go={go} />;
  else if (first === "p" && pid && section === "variables") page = <VariablesPage pid={pid} go={go} />;
  else if (first === "p" && pid && section === "access") page = <AccessPage pid={pid} go={go} />;
  else if (first === "decisions") page = <DecisionRoom me={me.data.name} go={go} />;
  else if (first === "overview") page = <OverviewPage go={go} />;
  else if (first === "admin") page = <AdminPage go={go} />;
  else if (first === "p" && pid && section === "audit") page = <AuditPage pid={pid} go={go} />;
  else if (first === "p" && pid && section === "runs" && id) page = <RunDetailPage pid={pid} runId={id} go={go} />;
  else if (first === "p" && pid) page = <RunsPage pid={pid} go={go} />;
  else page = <ProjectsPage go={go} />;

  return (
    <AppShell me={me.data} project={project} first={first} here={here} mine={mine} allMine={allMine} go={go}>
      <PageErrorBoundary resetKey={parts.join("/")}>{page}</PageErrorBoundary>
    </AppShell>
  );
}
