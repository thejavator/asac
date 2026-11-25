import { cn } from "@/lib/utils";

/** Static pipeline definition (no run state): steps left to right, the selected one is ringed. */
export function DefinitionFlow({ steps, current, onPick }: {
  steps: { id: string; agent?: string | null; gate_role?: string | null }[]; current?: string; onPick: (id: string) => void;
}) {
  return (
    <ol className="flex items-stretch overflow-x-auto p-1.5" aria-label={`Steps in order: ${steps.map((s) => s.id).join(", ")}`}>
      {steps.map((s, i) => (
        <li key={s.id} className="flex min-w-[11rem] flex-1 shrink-0 items-center">
          <button
            type="button"
            onClick={() => onPick(s.id)}
            aria-current={s.id === current ? "step" : undefined}
            className={cn(
              "grid flex-1 gap-0.5 rounded-lg border bg-card p-3 text-left transition-shadow hover:shadow-sm",
              "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
              s.id === current && "ring-2 ring-foreground/60",
            )}
          >
            <span className="truncate text-sm font-medium">{s.id}</span>
            <span className="truncate font-mono text-xs text-muted-foreground">{s.agent ?? "no agent"}</span>
            <span className={cn("truncate text-xs", s.gate_role ? "text-foreground" : "text-muted-foreground")}>
              {s.gate_role ? `gate: ${s.gate_role}` : "no gate"}
            </span>
          </button>
          {i < steps.length - 1 && <span aria-hidden="true" className="mx-1 h-px w-5 shrink-0 bg-foreground/30" />}
        </li>
      ))}
    </ol>
  );
}
