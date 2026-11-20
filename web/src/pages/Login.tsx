import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";

const ROLE_HINT: Record<string, string> = {
  product_owner: "Approves business decisions",
  auditor: "Reads everything, exports the audit",
  manager: "Follows runs and spend",
  developer: "Starts runs, edits pipelines",
};

/** Home page for signed-out visitors: what ASAC is, and the way in. */
export function LoginPage() {
  const opts = useQuery({
    queryKey: ["login-options"],
    queryFn: () => unwrap(api.GET("/login-options")),
  });

  return (
    <div className="welcome">
      <section className="welcome-pitch" aria-labelledby="pitch">
        <div className="brand">ASAC <small>governance</small></div>
        <h1 id="pitch">Every agent step, on the record.</h1>
        <p>
          Review what the agents produced, decide at each gate, and keep the evidence chain
          your auditors will ask for.
        </p>
        <ul className="welcome-points">
          <li><span className="chip" data-state="ok">Approved</span> by a named person with the right role</li>
          <li><span className="chip" data-state="wait">Waiting</span> until someone decides, never auto-approved</li>
          <li><span className="chip" data-state="bad">Rejected</span> with a comment that stays in the audit trail</li>
        </ul>
      </section>

      <main className="welcome-in">
        <h2>Sign in</h2>
        {opts.isPending && <p className="faint">Loading…</p>}
        {opts.isError && (
          <p role="alert" className="notice">Could not reach the portal: {opts.error.message}</p>
        )}
        {opts.data?.mode === "oidc" && (
          <>
            <p className="faint">
              {opts.data.organization ? `${opts.data.organization} uses single sign-on.` : "Use your organisation account."}
            </p>
            <a className="btn btn-primary welcome-sso" href="/login">Continue with single sign-on</a>
          </>
        )}
        {opts.data?.mode === "dev" && (
          <>
            <p className="notice" role="note">
              <span aria-hidden="true">!</span> Development mode. These are local test accounts, not real sign-in.
            </p>
            <ul className="personas">
              {opts.data.personas.map((p) => (
                <li key={p.id}>
                  <a className="persona" href={`/login?persona=${encodeURIComponent(p.id)}`}>
                    <b>{p.name}</b>
                    <span>{p.roles.map((r) => ROLE_HINT[r] ?? r).join(" · ")}</span>
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  );
}
