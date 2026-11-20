import { stepState } from "./Chip";

const SYM = { ok: "✓", wait: "◔", bad: "✕", stop: "■", idle: "○" } as const;

export function FlowGraph({ steps }: { steps: { id: string; status: string }[] }) {
  const w = 120;
  const gap = 30;
  const width = Math.max(640, steps.length * (w + gap) + 8);
  const names = steps.map((s) => `${s.id} ${stepState(s.status)[1]}`).join(", ");
  return (
    <div className="scroll-x">
      <svg
        className="graph"
        viewBox={`0 0 ${width} 110`}
        role="img"
        aria-label={`Pipeline: ${names}`}
      >
        {steps.slice(1).map((s, i) => (
          <path key={s.id} className="edge" d={`M${8 + i * (w + gap) + w} 55 H${8 + (i + 1) * (w + gap)}`} />
        ))}
        {steps.map((s, i) => {
          const [state, label] = stepState(s.status);
          const x = 8 + i * (w + gap);
          return (
            <g key={s.id} className="node" data-state={state}>
              <rect x={x} y={30} width={w} height={50} />
              <text x={x + 12} y={52}>{s.id}</text>
              <text className="sub" x={x + 12} y={68}>{`${SYM[state]} ${label.toLowerCase()}`}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
