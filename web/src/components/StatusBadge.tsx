import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { State } from "./Chip";

/** Same states as the legacy Chip. Each one still carries a symbol and a label, never color alone. */
const STYLE: Record<State, { symbol: string; className: string }> = {
  ok: { symbol: "✓", className: "bg-success/12 text-success border-success/25" },
  wait: { symbol: "◔", className: "bg-warning/12 text-warning border-warning/30" },
  bad: { symbol: "✕", className: "bg-destructive/10 text-destructive border-destructive/25" },
  stop: { symbol: "■", className: "bg-secondary text-secondary-foreground border-transparent" },
  idle: { symbol: "○", className: "bg-muted text-muted-foreground border-transparent" },
};

export function StatusBadge({ state, children, className }: { state: State; children: React.ReactNode; className?: string }) {
  const s = STYLE[state];
  return (
    <Badge variant="outline" className={cn(s.className, className)}>
      <span aria-hidden="true">{s.symbol}</span>
      {children}
    </Badge>
  );
}
