import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Chip } from "../components/Chip";
import { Link } from "../components/Link";

export function ProjectsPage({ go }: { go: (to: string) => void }) {
  const q = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/projects")) });
  return (
    <>
      <div className="page-head">
        <div>
          <h1>All projects</h1>
          <p>Projects you can see, with what needs attention.</p>
        </div>
      </div>
      {q.isError && <p role="alert">Could not load projects: {q.error.message}</p>}
      {q.data && q.data.length === 0 && <p className="soft">You have no access to any project yet. Ask an organisation admin to add you.</p>}
      {q.data && q.data.length > 0 && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr><th>Project</th><th>Your roles</th><th className="num">Active</th><th className="num">Problems</th><th className="num">Waiting for you</th></tr>
            </thead>
            <tbody>
              {q.data.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link to={`/p/${p.id}/runs`} go={go}>{p.name}</Link>{" "}
                    {p.error && <Chip state="bad">Unavailable</Chip>}
                  </td>
                  <td className="mono">{p.roles.join(", ") || "reader"}</td>
                  <td className="num">{p.active_runs}</td>
                  <td className="num">{p.problem_runs > 0 ? <Chip state="bad">{p.problem_runs}</Chip> : 0}</td>
                  <td className="num">{p.my_pending_gates > 0 ? <Chip state="wait">{p.my_pending_gates}</Chip> : 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
