import { Check, Circle, Loader, Square, X } from "lucide-react";
import { type ComponentType, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { type State, stepState } from "./Chip";

const ICON: Record<State, ComponentType<{ className?: string }>> = { ok: Check, wait: Loader, bad: X, stop: Square, idle: Circle };

const NODE: Record<State, string> = {
  ok: "border-success/40 bg-success/5",
  wait: "border-warning/50 bg-warning/5",
  bad: "border-destructive/50 bg-destructive/5",
  stop: "border-border bg-muted",
  idle: "border-dashed border-border bg-transparent text-muted-foreground",
};
const DOT: Record<State, string> = {
  ok: "bg-success/15 text-success",
  wait: "bg-warning/15 text-warning",
  bad: "bg-destructive/15 text-destructive",
  stop: "bg-secondary text-secondary-foreground",
  idle: "bg-muted text-muted-foreground",
};

/** Steps of a run as a left-to-right chain. Each node is a button that selects the step. */
export function PipelineFlow({
  steps, current, onPick,
}: { steps: { id: string; status: string }[]; current?: string; onPick: (id: string) => void }) {
  const list = useRef<HTMLOListElement>(null);
  // On a narrow screen the chain scrolls sideways: bring the selected step into view.
  useEffect(() => {
    // scroll only the chain, never the page: scrollIntoView would also move the window
    const box = list.current;
    const el = box?.querySelector<HTMLElement>('[aria-current="step"]');
    if (!box || !el) return;
    const target = el.offsetLeft - (box.clientWidth - el.offsetWidth) / 2;
    box.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
  }, [current]);
  const names = steps.map((s) => `${s.id} ${stepState(s.status)[1]}`).join(", ");
  return (
    <ol ref={list} className="flex w-full min-w-0 items-center overflow-x-auto p-1.5" aria-label={`Pipeline: ${names}`}>
      {steps.map((s, i) => {
        const [state, label] = stepState(s.status);
        const Icon = ICON[state];
        const next = steps[i + 1] && stepState(steps[i + 1]!.status)[0];
        return (
          <li key={s.id} className="flex min-w-[10.5rem] flex-1 shrink-0 items-center">
            <button
              type="button"
              onClick={() => onPick(s.id)}
              aria-current={s.id === current ? "step" : undefined}
              className={cn(
                "flex min-w-[8.5rem] flex-1 items-center gap-2.5 rounded-lg border p-2.5 text-left transition-shadow hover:shadow-sm",
                "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
                NODE[state],
                s.id === current && "ring-2 ring-foreground/60",
              )}
            >
              <span className={cn("grid size-6 shrink-0 place-items-center rounded-full", DOT[state])}>
                <Icon className="size-3.5" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{s.id}</span>
                <span className="block truncate text-xs text-muted-foreground">{label}</span>
              </span>
            </button>
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={cn("mx-1 h-px w-5 shrink-0", state === "ok" && next !== "idle" ? "bg-foreground/30" : "border-t border-dashed border-border")}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
