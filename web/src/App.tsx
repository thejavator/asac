import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, csrfHeader, setCsrf, unwrap, Unauthenticated } from "./api/client";
import { Link } from "./components/Link";
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
  if (me.isError) return <main className="main"><p role="alert">Could not load your session: {me.error.message}</p></main>;
  if (!me.data) return <main className="main"><p className="faint">Loading…</p></main>;

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
  else if (first === "admin") page = <AdminPage go={go} />;
  else if (first === "p" && pid && section === "audit") page = <AuditPage pid={pid} go={go} />;
  else if (first === "p" && pid && section === "runs" && id) page = <RunDetailPage pid={pid} runId={id} go={go} />;
  else if (first === "p" && pid) page = <RunsPage pid={pid} go={go} />;
  else page = <ProjectsPage go={go} />;

  return (
    <div className="shell">
      <aside className="rail" aria-label="Main navigation">
        <div className="brand">ASAC <small>governance</small></div>
        <div className="scope">
          <b>{project?.name ?? "All projects"}</b>
          <span>{me.data.organization}</span>
        </div>
        <nav>
          {project && (
            <ul className="nav">
              <li><Link to={`/p/${project.id}/runs`} go={go} current={here === "runs"}>Runs</Link></li>
              <li>
                <Link to={`/p/${project.id}/decisions`} go={go} current={here === "decisions"}>
                  Decision Room {mine > 0 && <span className="count">{mine}</span>}
                </Link>
              </li>
              <li><Link to={`/p/${project.id}/errors`} go={go} current={here === "errors"}>Errors {project.problem_runs > 0 && <span className="count">{project.problem_runs}</span>}</Link></li>
              <li><Link to={`/p/${project.id}/pipeline`} go={go} current={here === "pipeline"}>Pipeline</Link></li>
              <li><Link to={`/p/${project.id}/variables`} go={go} current={here === "variables"}>Variables</Link></li>
              <li><Link to={`/p/${project.id}/audit`} go={go} current={here === "audit"}>Audit trail</Link></li>
              {(project.roles.includes("owner") || me.data?.roles.includes("admin")) && (
                <li><Link to={`/p/${project.id}/access`} go={go} current={here === "access"}>Access</Link></li>
              )}
            </ul>
          )}
          <ul className="nav">
            <li><h2>Organisation</h2></li>
            <li><Link to="/" go={go} current={!project && first !== "decisions" && first !== "admin"}>All projects</Link></li>
            <li><Link to="/decisions" go={go} current={first === "decisions"}>Decision Room {allMine > 0 && <span className="count">{allMine}</span>}</Link></li>
            {me.data?.roles.includes("admin") && <li><Link to="/admin" go={go} current={first === "admin"}>Administration</Link></li>}
          </ul>
        </nav>
        <div className="who">
          <b>{me.data.name}</b>
          <span>{project ? `${project.roles.join(", ") || "reader"} · ${project.id}` : me.data.roles.join(", ")}</span>
          <button className="signout" type="button" onClick={() => {
            void api.POST("/logout", { headers: csrfHeader() }).then(() => window.location.assign("/app/"));
          }}>Sign out</button>
        </div>
      </aside>
      <main className="main">{page}</main>
    </div>
  );
}
