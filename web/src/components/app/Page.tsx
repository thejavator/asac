import { TriangleAlert } from "lucide-react";
import { Fragment } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Link } from "../Link";

/** Every page: same width, same vertical rhythm. */
export function Page({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return <div className={cn("mx-auto grid w-full grid-cols-[minmax(0,1fr)] gap-6", wide ? "max-w-7xl" : "max-w-6xl")}>{children}</div>;
}

/** Breadcrumb trail. The last entry is the current page; entries with `to` are links. */
export function Crumbs({ go, items }: { go: (to: string) => void; items: { label: React.ReactNode; to?: string; mono?: boolean }[] }) {
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {items.map((it, i) => (
          <Fragment key={i}>
            {i > 0 && <BreadcrumbSeparator />}
            <BreadcrumbItem>
              {it.to && i < items.length - 1 ? (
                <BreadcrumbLink asChild><Link to={it.to} go={go}>{it.label}</Link></BreadcrumbLink>
              ) : (
                <BreadcrumbPage className={it.mono ? "font-mono text-sm" : undefined}>{it.label}</BreadcrumbPage>
              )}
            </BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

export function PageHeader({ title, description, actions, badge }: {
  title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; badge?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="grid max-w-3xl gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          {badge}
        </div>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A card whose body is a full-bleed table. */
export function TableCard({ title, description, actions, children }: {
  title?: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <Card className="gap-0 overflow-hidden py-0">
      {(title || description || actions) && (
        <CardHeader className="flex flex-wrap items-start justify-between gap-2 border-b py-4">
          <div className="grid gap-1">
            {title && <CardTitle>{title}</CardTitle>}
            {description && <CardDescription>{description}</CardDescription>}
          </div>
          {actions}
        </CardHeader>
      )}
      {children}
    </Card>
  );
}

export function ErrorAlert({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <Alert variant="destructive" role="alert">
      <TriangleAlert />
      <AlertTitle>{title}</AlertTitle>
      {children && <AlertDescription>{children}</AlertDescription>}
    </Alert>
  );
}

/** Calm, non-error notice (permission note, dev mode, conflict explanation). */
export function Notice({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <Alert role="note">
      <TriangleAlert />
      {title && <AlertTitle>{title}</AlertTitle>}
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{children}</p>;
}

/** Secondary explanation under a heading or a control. */
export function Hint({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-sm text-muted-foreground", className)}>{children}</p>;
}

/** Inline code for keys, ids and paths. */
export function Code({ children }: { children: React.ReactNode }) {
  return <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{children}</code>;
}

/** Two-column label/value list (step inspector, facts). */
export function Fields({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(6rem,auto)_minmax(0,1fr)] gap-x-6 gap-y-2 text-sm">
      {rows.map(([k, v]) => (
        <Fragment key={k}>
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="m-0 break-words">{v}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

/** Text output (runner, hook, diff) in a scrollable block. */
export function Output({ children, className, label }: { children: React.ReactNode; className?: string; label?: string }) {
  return (
    <pre
      tabIndex={0}
      aria-label={label}
      className={cn(
        "max-h-72 overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words",
        "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
        className,
      )}
    >
      {children}
    </pre>
  );
}
