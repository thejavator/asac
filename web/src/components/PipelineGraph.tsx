import type { Schema } from "../api/client";

type Step = Schema["PipelineStepOut"];

/** Steps left to right with the gate role under each; the selected step is marked. */
export function PipelineGraph({ steps, current, onPick }: { steps: Step[]; current?: string; onPick: (id: string) => void }) {
  const w = 150, gap = 80;
  return (
    <div className="scroll-x">
      <svg className="pipe-graph" viewBox={`0 0 ${Math.max(1, steps.length) * (w + gap) - gap + 16} 100`} role="img"
           aria-label={`Steps in order: ${steps.map((s) => s.id).join(", ")}`}>
        {steps.slice(1).map((s, i) => <path key={s.id} className="edge" d={`M${8 + i * (w + gap) + w} 42 H${8 + (i + 1) * (w + gap)}`} />)}
        {steps.map((s, i) => {
          const x = 8 + i * (w + gap);
          return (
            <g key={s.id} className="node" data-state="idle" aria-current={s.id === current ? "step" : undefined}
               tabIndex={0} role="button" onClick={() => onPick(s.id)}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onPick(s.id); }}>
              <rect x={x} y={10} width={w} height={66} rx={6} />
              <text x={x + 12} y={32}>{s.id}</text>
              <text className="sub" x={x + 12} y={50}>{s.agent ?? "no agent"}</text>
              <text className="sub" x={x + 12} y={66}>{s.gate_role ? `gate: ${s.gate_role}` : "no gate"}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
