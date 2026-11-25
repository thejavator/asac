import { useQuery } from "@tanstack/react-query";
import { KeyRound, Loader2 } from "lucide-react";
import { api, unwrap } from "../api/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "../components/StatusBadge";

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
    <div className="grid min-h-screen bg-background lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section aria-labelledby="pitch" className="grid content-center gap-6 bg-muted/40 p-8 lg:p-16">
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-semibold tracking-tight">ASAC</span>
          <span className="text-sm text-muted-foreground">governance</span>
        </div>
        <h1 id="pitch" className="max-w-xl text-4xl font-semibold tracking-tight text-balance">Every agent step, on the record.</h1>
        <p className="max-w-lg text-muted-foreground">
          Review what the agents produced, decide at each gate, and keep the evidence chain your auditors will ask for.
        </p>
        <ul className="grid max-w-lg gap-3 text-sm">
          <li className="flex items-center gap-3"><StatusBadge state="ok">Approved</StatusBadge> by a named person with the right role</li>
          <li className="flex items-center gap-3"><StatusBadge state="wait">Waiting</StatusBadge> until someone decides, never auto-approved</li>
          <li className="flex items-center gap-3"><StatusBadge state="bad">Rejected</StatusBadge> with a comment that stays in the audit trail</li>
        </ul>
      </section>

      <main className="grid content-center p-8 lg:p-16">
        <Card className="mx-auto w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-xl">Sign in</CardTitle>
            <CardDescription>
              {opts.data?.mode === "oidc" && (opts.data.organization ? `${opts.data.organization} uses single sign-on.` : "Use your organisation account.")}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {opts.isPending && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading…</p>}
            {opts.isError && (
              <Alert variant="destructive" role="alert">
                <AlertTitle>Could not reach the portal</AlertTitle>
                <AlertDescription>{opts.error.message}</AlertDescription>
              </Alert>
            )}
            {opts.data?.mode === "oidc" && (
              <Button asChild size="lg"><a href="/login"><KeyRound /> Continue with single sign-on</a></Button>
            )}
            {opts.data?.mode === "dev" && (
              <>
                <Alert role="note">
                  <AlertTitle>Development mode</AlertTitle>
                  <AlertDescription>These are local test accounts, not real sign-in.</AlertDescription>
                </Alert>
                <ul className="grid gap-2">
                  {opts.data.personas.map((p) => (
                    <li key={p.id}>
                      <Button asChild variant="outline" className="h-auto w-full justify-start px-4 py-3 text-left">
                        <a href={`/login?persona=${encodeURIComponent(p.id)}`}>
                          <span className="grid gap-0.5">
                            <span className="font-medium">{p.name}</span>
                            <span className="flex flex-wrap gap-1">
                              {p.roles.map((r) => <Badge key={r} variant="secondary" className="font-normal">{ROLE_HINT[r] ?? r}</Badge>)}
                            </span>
                          </span>
                        </a>
                      </Button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
