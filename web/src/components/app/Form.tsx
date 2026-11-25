import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** Label + control + optional hint, stacked. */
export function Field({ id, label, hint, children, className }: {
  id: string; label: React.ReactNode; hint?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("grid gap-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p id={`${id}-hint`} className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** Footer of a form: actions left, a short note right. */
export function FormActions({ children, note }: { children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {children}
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  );
}
